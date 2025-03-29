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
from webdriver_manager.chrome import ChromeDriverManager

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
MAX_ROWS = 50
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

def init_driver():
    """初始化浏览器驱动"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    options.add_argument(f"--user-data-dir=/tmp/chrome-{time.time()}")  # 唯一目录
    
    # 使用webdriver-manager自动管理驱动
    driver = webdriver.Chrome(ChromeDriverManager().install(), options=options)
    return driver

def fetch_ips():
    """获取IP列表"""
    driver = None
    try:
        driver = init_driver()
        driver.get(URL)
        
        # 关键修复：正确的等待语法
    try:
        # 等待表格加载完成
        WebDriverWait(driver, REQUEST_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )
    
        # 检查表格中是否有足够的数据行（可选）
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "tr")) > 1
        )
    except Exception as e:
        logger.error(f"等待元素超时: {e}")
        return None

        # 页面解析逻辑（保持原有代码不变）
        soup = BeautifulSoup(driver.page_source, "html.parser")
        table = soup.find("table")
        if not table:
            return None

        ip_list = []
        for row in table.find_all("tr")[1:MAX_ROWS+1]:
            cols = row.find_all("td")
            if len(cols) >= 6:
                ip = cols[1].text.strip()
                if validate_ip(ip):
                    ip_list.append({
                        "ip": ip,
                        "port": "443",
                        "region": cols[4].text.strip() if len(cols) > 4 else "UNKNOWN"
                    })
        return ip_list

    except Exception as e:
        logger.error(f"抓取异常: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def validate_ip(ip):
    """验证IP格式"""
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return len(parts) == 8
    else:  # IPv4
        parts = ip.split(".")
        return len(parts) == 4 and all(p.isdigit() for p in parts)

# [保持原有的国家代码查询和保存函数不变]

if __name__ == "__main__":
    logger.info("开始执行IP抓取任务")
    ips = fetch_ips()
    if ips:
        logger.info(f"成功获取 {len(ips)} 个IP")
        # 保存结果...
    else:
        logger.error("未能获取有效IP列表")
