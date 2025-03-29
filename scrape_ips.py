import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import geoip2.database
import os
import logging
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

URL = "https://cf.vvhan.com/"
OUTPUT_FILE = "ip.txt"
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

# 地区到国家代码的映射表
REGION_TO_COUNTRY = {
    "SEA": "SG",  # 东南亚 -> 新加坡
    "NRT": "JP",  # 成田 -> 日本
    "LAX": "US",  # 洛杉矶 -> 美国
    "FRA": "DE",  # 法兰克福 -> 德国
    "SJC": "US",  # 圣何塞 -> 美国
    "IAD": "US",  # 华盛顿杜勒斯 -> 美国
    "AMS": "NL",  # 阿姆斯特丹 -> 荷兰
    "Default": "UNKNOWN"
}

MAX_ROWS = 50  # 最大抓取行数

def is_valid_ip(ip):
    """验证 IPv4/IPv6 地址是否合法"""
    if ":" in ip:
        parts = ip.split(":")
        return len(parts) == 8 and all(re.match(r"^[0-9a-fA-F]{1,4}$", p) for p in parts)
    else:
        parts = ip.split(".")
        return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

def fetch_ips_with_selenium():
    try:
        logger.info(f"正在从 {URL} 抓取 IP 列表...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=options)
        driver.get(URL)

        # 等待表格加载
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
        WebDriverWait(driver, 30).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "tr")) > 1
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table")
        if not table:
            logger.error("未找到表格！")
            return []

        ip_list = []
        rows = table.find_all("tr")[1:]  # 跳过表头
        for row in rows[:MAX_ROWS] if MAX_ROWS > 0 else rows:
            cols = row.find_all("td")
            if len(cols) < 2:
                continue

            # 提取 IP 和线路名称
            ip = cols[1].text.strip()  # 假设第二列是IP
            line_name = cols[0].text.strip() or "未知线路"
            
            if not is_valid_ip(ip):
                continue

            # 提取地区（假设第五列是地区）
            region = cols[4].text.strip() if len(cols) >= 5 else "UNKNOWN"
            country = REGION_TO_COUNTRY.get(region, "UNKNOWN")

            # 格式化为 ip:端口#线路-国家代码
            ip_port = f"{ip}:443#{line_name}-{country}"
            ip_list.append(ip_port)

        driver.quit()
        return ip_list

    except Exception as e:
        logger.error(f"抓取失败: {e}")
        return []

def save_ips(ip_list):
    # 去重并写入文件
    unique_ips = list(set(ip_list))
    with open(OUTPUT_FILE, "w") as f:
        for ip in unique_ips:
            f.write(f"{ip}\n")
    logger.info(f"已保存 {len(unique_ips)} 个 IP 到 {OUTPUT_FILE}")

if __name__ == "__main__":
    ips = fetch_ips_with_selenium()
    if ips:
        save_ips(ips)
    else:
        logger.error("未获取到有效 IP 列表！")
