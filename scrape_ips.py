import requests
from bs4 import BeautifulSoup
import re
import geoip2.database
import os
import logging
import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse
from webdriver_manager.chrome import ChromeDriverManager

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
REQUEST_TIMEOUT = 45  # 增加超时时间
DELAY_RANGE = (1, 3)  # 随机延迟范围

# 地区到国家代码映射
REGION_TO_COUNTRY = {
    "SEA": "SG", "NRT": "JP", "LAX": "US", "FRA": "DE",
    "SJC": "US", "IAD": "US", "AMS": "NL", "Default": "UNKNOWN"
}

def initialize_driver():
    """初始化Selenium驱动（使用webdriver-manager自动管理驱动）"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    options.add_argument(f"--user-data-dir=/tmp/chrome-{time.time()}")  # 唯一用户目录
    
    # 使用webdriver-manager自动管理ChromeDriver
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    return driver

def is_valid_ip(ip):
    """增强版IP验证"""
    if not ip:
        return False
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        if len(parts) != 8:
            return False
        return all(re.match(r"^[0-9a-fA-F]{0,4}$", p) for p in parts)
    else:  # IPv4
        parts = ip.split(".")
        if len(parts) != 4:
            return False
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

def get_site_name(url):
    """从URL提取网站名称"""
    try:
        domain = urlparse(url).netloc
        return domain.split('.')[-2] if '.' in domain else domain
    except:
        return "unknown"

def fetch_from_website(driver, url):
    """从单个网站抓取IP（增强稳定性）"""
    site_name = get_site_name(url)
    logger.info(f"开始抓取 {site_name} ({url})")
    
    try:
        # 随机延迟防止被ban
        time.sleep(random.uniform(*DELAY_RANGE))
        
        driver.get(url)
        WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table, .table, [class*='table'], .ip-list"))
        
        # 添加DOM就绪检查
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete")
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")
        
        if not tables:
            logger.info(f"{site_name} 未找到表格，尝试文本提取")
            return extract_ips_from_text(driver.page_source, site_name)
        
        return parse_table_data(tables[0], site_name)
    
    except Exception as e:
        logger.error(f"{site_name} 抓取失败: {str(e)[:200]}")
        driver.save_screenshot(f"error_{site_name}.png")
        return None

def extract_ips_from_text(content, site_name):
    """增强版文本IP提取"""
    ip_pattern = r"(?:\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4})"
    ip_matches = re.findall(ip_pattern, content)
    
    if ip_matches:
        ips = []
        for ip in ip_matches:
            if is_valid_ip(ip):
                ips.append({
                    "ip_with_port": f"{ip}:443", 
                    "region": "UNKNOWN", 
                    "line_name": f"{site_name}-文本提取"
                })
        logger.info(f"从 {site_name} 文本中找到 {len(ips)} 个有效IP")
        return ips
    
    logger.warning(f"{site_name} 未找到有效IP地址")
    return None

def parse_table_data(table, site_name):
    """增强版表格解析"""
    ip_list = []
    rows = table.find_all("tr")[1:]  # 跳过表头
    
    for row in rows[:MAX_ROWS]:
        cols = row.find_all("td")
        if len(cols) < 2:  # 最少需要IP列
            continue

        try:
            ip = cols[1].text.strip()
            if not is_valid_ip(ip):
                continue

            # 动态列处理
            region = (cols[4].text.strip() if len(cols) > 4 else 
                     cols[3].text.strip() if len(cols) > 3 else "Default")
            line_name = (cols[0].text.strip() or 
                        f"{site_name}-线路-{len(ip_list)+1}")
            
            # 延迟检查（宽松处理）
            latency = None
            if len(cols) > 2:
                try:
                    latency = float(cols[2].text.replace("ms", "").strip())
                    if latency > 1000:  # 宽松的延迟阈值
                        continue
                except:
                    pass
            
            ip_list.append({
                "ip_with_port": f"{ip}:443",
                "region": region[:20],  # 限制长度
                "line_name": line_name[:30]
            })

        except Exception as e:
            logger.warning(f"解析行数据出错: {e}")
            continue

    logger.info(f"从 {site_name} 表格中解析到 {len(ip_list)} 个有效IP")
    return ip_list

def fetch_all_ips():
    """从所有网站抓取IP（带重试和验证）"""
    driver = None
    all_ips = []
    
    try:
        driver = initialize_driver()
        
        for url in [u.strip() for u in URLS.split(",") if u.strip()]:
            logger.info(f"处理URL: {url}")
            
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    ips = fetch_from_website(driver, url)
                    if ips:
                        all_ips.extend(ips)
                        if len(ips) >= MIN_IPS / len(URLS.split(",")):
                            break
                    
                    logger.warning(f"第 {attempt} 次尝试获取IP不足 ({len(ips) if ips else 0})")
                    if attempt < MAX_RETRIES:
                        time.sleep(attempt * 2)  # 递增延迟
                
                except Exception as e:
                    logger.error(f"尝试 {attempt} 失败: {str(e)[:200]}")
                    if driver:
                        driver.save_screenshot(f"retry_{attempt}.png")
    
    finally:
        if driver:
            driver.quit()
    
    return all_ips if len(all_ips) >= MIN_IPS else None

# [保持原有的get_country_code系列函数不变]

def save_ips(ip_list):
    """保存IP列表（增强版去重和格式处理）"""
    if not ip_list:
        logger.error("没有有效的IP可保存")
        return

    # 多维度去重
    unique_ips = []
    seen_ips = set()
    
    for entry in sorted(ip_list, key=lambda x: x["ip_with_port"]):
        ip_port = entry["ip_with_port"]
        if ip_port not in seen_ips:
            seen_ips.add(ip_port)
            
            # 处理国家代码
            ip, port = ip_port.split(":")
            country = get_country_code(ip, entry["region"])
            
            # 格式化输出
            tag = f"{entry['line_name']}-{country}"
            unique_ips.append(f"{ip}:{port}#{tag}")

    # 写入文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(unique_ips) + "\n")
    
    logger.info(f"成功保存 {len(unique_ips)} 个唯一IP到 {OUTPUT_FILE}")

def main():
    """主入口函数"""
    try:
        logger.info("="*50)
        logger.info(f"开始抓取 {URLS} 的IP列表")
        logger.info("="*50)
        
        ip_list = fetch_all_ips()
        if not ip_list:
            logger.error(f"未能获取足够IP (最少需要 {MIN_IPS} 个)")
            return 1
        
        save_ips(ip_list)
        return 0
    
    except Exception as e:
        logger.error(f"主程序错误: {str(e)}", exc_info=True)
        return 1
    finally:
        logger.info("="*50)
        logger.info("程序执行完毕")
        logger.info("="*50)

if __name__ == "__main__":
    exit(main())
