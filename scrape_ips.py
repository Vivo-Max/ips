import requests
from bs4 import BeautifulSoup
import re
import geoip2.database
import os
import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 常量配置
URLS = "https://cf.vvhan.com/"  # 逗号分隔的多个目标网站
OUTPUT_FILE = "ip.txt"
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# 配置参数
MAX_ROWS = 100
MAX_RETRIES = 3
MIN_IPS = 15
REQUEST_TIMEOUT = 30

# 地区到国家代码映射
REGION_TO_COUNTRY = {
    "SEA": "SG", "NRT": "JP", "LAX": "US", "FRA": "DE",
    "SJC": "US", "IAD": "US", "AMS": "NL", "Default": "UNKNOWN"
}

def initialize_driver():
    """初始化Selenium驱动"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    return webdriver.Chrome(options=options)

def is_valid_ip(ip):
    """验证IP地址是否合法"""
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return len(parts) == 8 and all(re.match(r"^[0-9a-fA-F]{1,4}$", p) for p in parts)
    else:  # IPv4
        parts = ip.split(".")
        return (len(parts) == 4 and 
                all(p.isdigit() and 0 <= int(p) <= 255 for p in parts))

def get_site_name(url):
    """从URL提取网站名称"""
    domain = urlparse(url).netloc
    return domain.split('.')[-2] if '.' in domain else domain

def fetch_from_website(driver, url):
    """从单个网站抓取IP"""
    site_name = get_site_name(url)
    logger.info(f"开始抓取 {site_name} ({url})")
    
    try:
        driver.get(url)
        WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table, .table, [class*='table']"))
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            return extract_ips_from_text(driver.page_source, site_name)
        
        return parse_table_data(tables[0], site_name)  # 只处理第一个表格
    
    except Exception as e:
        logger.error(f"{site_name} 抓取失败: {str(e)[:200]}")
        driver.save_screenshot(f"error_{site_name}.png")
        return None

def extract_ips_from_text(content, site_name):
    """从页面文本中提取IP"""
    ip_pattern = r"\b(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    ip_matches = re.findall(ip_pattern, content)
    
    if ip_matches:
        logger.info(f"从 {site_name} 文本中找到 {len(ip_matches)} 个IP")
        return [{
            "ip_with_port": f"{ip}:443", 
            "region": "UNKNOWN", 
            "line_name": f"{site_name}-文本提取"
        } for ip in ip_matches if is_valid_ip(ip)]
    
    logger.warning(f"{site_name} 未找到IP地址")
    return None

def parse_table_data(table, site_name):
    """解析表格数据"""
    ip_list = []
    rows = table.find_all("tr")[1:]  # 跳过表头
    
    for row in rows[:MAX_ROWS]:
        cols = row.find_all("td")
        if len(cols) < 2:  # 至少需要IP和地区两列
            continue

        try:
            ip = cols[1].text.strip()
            if not is_valid_ip(ip):
                continue

            # 处理不同网站的不同列结构
            region = cols[4].text.strip() if len(cols) > 4 else "Default"
            line_name = cols[0].text.strip() if cols[0].text.strip() else f"{site_name}-线路"
            
            ip_list.append({
                "ip_with_port": f"{ip}:443",
                "region": region,
                "line_name": line_name
            })

        except Exception as e:
            logger.warning(f"解析行数据出错: {e}")
            continue

    logger.info(f"从 {site_name} 表格中解析到 {len(ip_list)} 个IP")
    return ip_list

def fetch_all_ips():
    """从所有网站抓取IP"""
    driver = initialize_driver()
    all_ips = []
    
    try:
        for url in URLS.split(','):
            url = url.strip()
            if not url:
                continue
                
            for attempt in range(MAX_RETRIES):
                ips = fetch_from_website(driver, url)
                if ips:
                    all_ips.extend(ips)
                    break
                logger.warning(f"{url} 第 {attempt+1} 次尝试失败")
                time.sleep(2)
    
    finally:
        driver.quit()
    
    return all_ips if len(all_ips) >= MIN_IPS else None

# [保持原有的get_country_code_from_db、get_country_code_from_api、get_country_code_from_region函数不变]

def get_country_code(ip, region):
    """获取国家代码（带缓存和回退）"""
    country = get_country_code_from_db(ip)
    if country != "UNKNOWN":
        return country
    
    logger.info(f"GeoLite2查询失败，尝试API查询 {ip}...")
    country = get_country_code_from_api(ip)
    return country if country != "UNKNOWN" else get_country_code_from_region(region)

def save_ips(ip_list):
    """保存IP列表（使用ip:端口#标签格式）"""
    if not ip_list:
        logger.error("没有有效的IP可保存")
        return

    unique_ips = []
    seen = set()
    
    for entry in ip_list:
        ip_port = entry["ip_with_port"]
        if ip_port not in seen:
            seen.add(ip_port)
            unique_ips.append(entry)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for entry in unique_ips:
            ip, port = entry["ip_with_port"].split(":")
            country = get_country_code(ip, entry["region"])
            tag = f"{entry['line_name']}-{country}"
            f.write(f"{ip}:{port}#{tag}\n")
    
    logger.info(f"成功保存 {len(unique_ips)} 个唯一IP到 {OUTPUT_FILE}")

def main():
    """主函数"""
    logger.info(f"开始从 {URLS} 抓取IP列表...")
    
    ip_list = fetch_all_ips()
    if not ip_list:
        logger.error("未能获取足够数量的有效IP")
        return

    save_ips(ip_list)
    logger.info("所有网站抓取完成")

if __name__ == "__main__":
    main()
