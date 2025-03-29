import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import geoip2.database
import os
import logging
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# 常量配置
URL = "https://cf.vvhan.com/"
OUTPUT_FILE = "ip.txt"
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# 配置参数
MAX_ROWS = 100  # 增加最大抓取行数
MAX_RETRIES = 3  # 最大重试次数
MIN_IPS = 15     # 最少需要获取的IP数量

# 地区到国家代码映射
REGION_TO_COUNTRY = {
    "SEA": "SG", "NRT": "JP", "LAX": "US", "FRA": "DE",
    "SJC": "US", "IAD": "US", "AMS": "NL", "Default": "UNKNOWN"
}

def is_valid_ip(ip):
    """验证IP地址是否合法"""
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return len(parts) == 8 and all(re.match(r"^[0-9a-fA-F]{1,4}$", p) for p in parts)
    else:  # IPv4
        parts = ip.split(".")
        return (len(parts) == 4 and 
                all(p.isdigit() and 0 <= int(p) <= 255 for p in parts))

def fetch_ips_with_selenium():
    """使用Selenium获取IP列表"""
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={HEADERS['User-Agent']}")

        driver = webdriver.Chrome(options=options)
        driver.get(URL)

        # 增强型等待条件
        try:
            WebDriverWait(driver, 45).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tr:nth-child(2)"))
        except Exception as e:
            logger.error(f"等待表格超时: {e}")
            driver.save_screenshot("timeout.png")
            driver.quit()
            return None

        # 解析表格数据
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table") or next(
            (div.find("table") for div in soup.find_all("div", class_=re.compile("table|ip-list"))), None)
        
        if not table:
            return extract_ips_from_text(driver.page_source, driver)

        return parse_table_data(table, driver)

    except Exception as e:
        logger.error(f"Selenium错误: {e}")
        return None

def extract_ips_from_text(content, driver):
    """从页面文本中提取IP（备用方法）"""
    ip_pattern = r"\b(?:\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    ip_matches = re.findall(ip_pattern, content)
    if ip_matches:
        logger.info(f"从文本中找到 {len(ip_matches)} 个IP")
        return [{"ip_with_port": f"{ip}:443", "region": "UNKNOWN", "line_name": "未知线路"} 
                for ip in ip_matches if is_valid_ip(ip)]
    logger.warning("未找到任何IP地址")
    driver.quit()
    return None

def parse_table_data(table, driver):
    """解析表格数据"""
    ip_list = []
    rows = table.find_all("tr")[1:]  # 跳过表头
    
    for row in rows[:MAX_ROWS]:
        cols = row.find_all("td")
        if len(cols) < 6:
            continue

        try:
            ip = cols[1].text.strip()
            if not is_valid_ip(ip):
                continue

            # 放宽延迟检查
            latency = cols[2].text.strip()
            try:
                if float(latency.replace("ms", "")) > 500:  # 延迟阈值提高到500ms
                    continue
            except ValueError:
                pass  # 忽略无效延迟数据

            # 处理地区信息
            region = cols[4].text.strip() or "Default"
            
            ip_list.append({
                "ip_with_port": f"{ip}:443",
                "region": region,
                "line_name": cols[0].text.strip() or "未知线路"
            })

        except Exception as e:
            logger.warning(f"解析行数据出错: {e}")
            continue

    driver.quit()
    logger.info(f"从表格中解析到 {len(ip_list)} 个IP")
    return ip_list

def fetch_ips():
    """获取IP列表（带重试机制）"""
    for attempt in range(MAX_RETRIES):
        ip_list = fetch_ips_with_selenium()
        if ip_list and len(ip_list) >= MIN_IPS:
            return ip_list
        logger.warning(f"第 {attempt+1} 次尝试获取IP数量不足 ({len(ip_list) if ip_list else 0})")
        time.sleep(5)
    return []

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
            # 使用 ip:端口#标签 格式
            f.write(f"{ip}:{port}#{tag}\n")
    
    logger.info(f"成功保存 {len(unique_ips)} 个IP到 {OUTPUT_FILE}")

def main():
    """主函数"""
    logger.info("开始抓取IP列表...")
    
    ip_list = fetch_ips()
    if not ip_list:
        logger.error("未能获取有效IP列表")
        return

    save_ips(ip_list)
    logger.info("任务完成")

if __name__ == "__main__":
    main()
