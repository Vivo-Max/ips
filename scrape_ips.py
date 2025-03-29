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

# 配置日志，仅输出到终端
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

URL = "https://cf.vvhan.com/"
OUTPUT_FILE = "ip.txt"
GEOIP_DB_PATH = "GeoLite2-Country.mmdb"  # 确保此路径正确
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

# 最大抓取行数（0 表示不限制）
MAX_ROWS = 50

# 地区到国家代码的映射表
REGION_TO_COUNTRY = {
    "SEA": "SG",  # 东南亚 -> 新加坡
    "NRT": "JP",  # 成田 -> 日本
    "LAX": "US",  # 洛杉矶 -> 美国
    "FRA": "DE",  # 法兰克福 -> 德国
    "SJC": "US",  # 圣何塞 -> 美国
    "IAD": "US",  # 华盛顿杜勒斯 -> 美国
    "AMS": "NL",  # 阿姆斯特丹 -> 荷兰
    "Default": "UNKNOWN"  # 默认值
}

def is_valid_ipv4(ip):
    """验证 IPv4 地址是否合法"""
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or int(part) < 0 or int(part) > 255:
            return False
    return True

def is_valid_ipv6(ip):
    """验证 IPv6 地址是否合法（简化版）"""
    parts = ip.split(":")
    if len(parts) != 8:
        return False
    for part in parts:
        if not re.match(r"^[0-9a-fA-F]{1,4}$", part):
            return False
    return True

def fetch_ips_with_selenium():
    try:
        logger.info(f"正在使用 selenium 从 {URL} 抓取 IP 列表...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={HEADERS['User-Agent']}")
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(options=options)
        driver.get(URL)

        # 显式等待，直到表格元素出现且至少有 2 行（表头 + 至少 1 行数据）
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            WebDriverWait(driver, 30).until(
                lambda d: len(d.find_elements(By.TAG_NAME, "tr")) > 1
            )
        except Exception as e:
            logger.error(f"等待表格元素超时或无数据行：{e}")
            logger.error("当前页面内容（前1000字符）：")
            logger.error(driver.page_source[:1000])
            driver.quit()
            return None

        content = driver.page_source
        logger.info("selenium 渲染后的网页内容（前1000字符）：")
        logger.info(content[:1000])

        soup = BeautifulSoup(content, "html.parser")
        table = soup.find("table")
        if not table:
            logger.info("未找到 IP 表格！尝试查找包含 IP 的 div...")
            divs = soup.find_all("div", class_=re.compile("table-responsive|ip-list|data-table|table"))
            for div in divs:
                table = div.find("table")
                if table:
                    break
        if not table:
            logger.info("未找到 IP 表格！尝试查找包含 IP 的文本...")
            ip_pattern = r"(?:\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4})"
            ip_matches = re.findall(ip_pattern, content)
            if ip_matches:
                logger.info(f"找到 {len(ip_matches)} 个 IP 地址（未提取地区）。")
                ip_list = []
                for ip in ip_matches:
                    ip_with_port = f"{ip}:443"
                    ip_entry = {"ip_with_port": ip_with_port, "region": "UNKNOWN", "line_name": "未知线路"}
                    ip_list.append(ip_entry)
                driver.quit()
                return ip_list
            logger.info("未找到任何 IP 地址！")
            driver.quit()
            return None

        logger.info("找到表格，内容如下（前500字符）：")
        logger.info(str(table)[:500])
        ip_list = []
        rows = table.find_all("tr")[1:]  # 跳过表头
        row_count = 0
        for row in rows:
            if MAX_ROWS > 0 and row_count >= MAX_ROWS:
                logger.info(f"已达到最大抓取行数 {MAX_ROWS}，停止解析。")
                break
            cols = row.find_all("td")
            if len(cols) < 6:  # 表格有 6 列
                logger.info(f"行数据不足（需要 6 列，实际 {len(cols)} 列），跳过：{row}")
                continue

            # 打印每一行的列内容，方便调试
            logger.info(f"行内容：{[col.text.strip() for col in cols]}")

            # 提取线路名称（第一列）
            line_name = cols[0].text.strip()
            if not line_name:
                line_name = "未知线路"

            # 提取 IP 地址（第二列）
            ip = cols[1].text.strip()
            if ":" in ip:
                if not is_valid_ipv6(ip):
                    logger.info(f"无效 IPv6 格式，跳过：{ip}")
                    continue
            else:
                if not is_valid_ipv4(ip):
                    logger.info(f"无效 IPv4 格式，跳过：{ip}")
                    continue

            # 提取延迟（第三列）
            latency = cols[2].text.strip()
            if "ms" not in latency:
                logger.info(f"延迟格式不正确（缺少 'ms'），跳过：{ip}")
                continue
            try:
                latency_ms = float(latency.replace("ms", ""))
                if latency_ms >= 200:
                    logger.info(f"延迟 {latency_ms}ms 过高，跳过：{ip}")
                    continue
            except ValueError as e:
                logger.info(f"无法解析延迟值（{latency}），跳过：{ip}，错误：{e}")
                continue

            # 提取地区（第五列）
            region = cols[4].text.strip()
            if not region or region.lower() == "default":
                logger.info(f"地区信息无效（{region}），跳过：{ip}")
                continue

            ip_with_port = f"{ip}:443"
            ip_entry = {"ip_with_port": ip_with_port, "region": region, "line_name": line_name}
            ip_list.append(ip_entry)
            row_count += 1

        driver.quit()
        logger.info(f"抓取到 {len(ip_list)} 个 IP 地址（未去重）。")
        return ip_list

    except Exception as e:
        logger.error(f"使用 selenium 抓取失败：{e}")
        return None

def fetch_ips():
    ip_list = fetch_ips_with_selenium()
    if ip_list is not None:
        return ip_list
    logger.error("selenium 抓取失败，无法获取 IP 列表。")
    return []

def get_country_code_from_db(ip):
    """使用 GeoLite2-Country.mmdb 查询 IP 地址的国家代码"""
    if not os.path.exists(GEOIP_DB_PATH):
        logger.error(f"GeoLite2-Country.mmdb 文件不存在，路径：{GEOIP_DB_PATH}")
        return "UNKNOWN"

    try:
        logger.info(f"正在使用 GeoLite2-Country.mmdb 查询 IP {ip} 的国家代码...")
        reader = geoip2.database.Reader(GEOIP_DB_PATH)
        response = reader.country(ip)
        country_code = response.country.iso_code
        logger.info(f"IP {ip} 的 GeoLite2 响应：{response}")
        reader.close()
        if not country_code:
            logger.warning(f"IP {ip} 的国家代码为空，返回 'UNKNOWN'")
            return "UNKNOWN"
        logger.info(f"IP {ip} 的国家代码（GeoLite2）：{country_code}")
        return country_code
    except geoip2.errors.AddressNotFoundError:
        logger.warning(f"IP {ip} 未找到国家信息（GeoLite2），返回 'UNKNOWN'")
        return "UNKNOWN"
    except Exception as e:
        logger.error(f"查询国家信息失败（GeoLite2）：{e}，IP: {ip}，返回 'UNKNOWN'")
        return "UNKNOWN"

def get_country_code_from_api(ip):
    """使用在线 API 查询 IP 地址的国家代码（备用方案）"""
    for attempt in range(3):  # 重试 3 次
        try:
            logger.info(f"正在使用在线 API 查询 IP {ip} 的国家代码（尝试 {attempt + 1}/3）...")
            url = f"http://ip-api.com/json/{ip}?fields=countryCode"
            response = requests.get(url, timeout=15, proxies=None, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "success":
                country_code = data.get("countryCode")
                if country_code:
                    logger.info(f"IP {ip} 的国家代码（API）：{country_code}")
                    return country_code
                else:
                    logger.warning(f"IP {ip} 的国家代码为空（API），返回 'UNKNOWN'")
                    return "UNKNOWN"
            else:
                logger.warning(f"IP {ip} 查询失败（API），返回 'UNKNOWN'")
                return "UNKNOWN"
        except requests.exceptions.RequestException as e:
            logger.error(f"在线 API 查询失败：{e}，IP: {ip}")
            if attempt == 2:  # 最后一次尝试
                logger.error("重试 3 次后仍失败，返回 'UNKNOWN'")
                return "UNKNOWN"
            continue

def get_country_code_from_region(region):
    """根据表格中的地区代码推测国家代码"""
    return REGION_TO_COUNTRY.get(region, "UNKNOWN")

def get_country_code(ip, region):
    """尝试使用 GeoLite2-Country.mmdb 查询国家代码，如果失败则使用在线 API，最后使用地区推测"""
    country = get_country_code_from_db(ip)
    if country != "UNKNOWN":
        return country

    logger.info(f"GeoLite2 查询失败，尝试使用在线 API 查询 IP {ip}...")
    country = get_country_code_from_api(ip)
    if country != "UNKNOWN":
        return country

    logger.info(f"在线 API 查询失败，尝试使用地区 {region} 推测国家代码...")
    country = get_country_code_from_region(region)
    logger.info(f"根据地区 {region} 推测的国家代码：{country}")
    return country

def save_ips(ip_list):
    seen = set()
    unique_ips = []
    for entry in ip_list:
        ip_port = entry["ip_with_port"]
        if ip_port not in seen:
            seen.add(ip_port)
            unique_ips.append(entry)
    logger.info(f"去重后剩余 {len(unique_ips)} 个 IP 地址。")

    server_port_pairs = []
    for entry in unique_ips:
        ip_port = entry["ip_with_port"]
        line_name = entry["line_name"]
        region = entry["region"]
        server, port = ip_port.split(":")
        country = get_country_code(server, region)
        tag = f"{line_name}-{country}"
        server_port_pairs.append((server, port, tag))

    if server_port_pairs:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for server, port, tag in server_port_pairs:
                f.write(f"{server}:{port}#{tag}\n")  # 修改为ip:端口#标签格式
        logger.info(f"已将 {len(server_port_pairs)} 个 IP 地址写入 {OUTPUT_FILE}。")
    else:
        logger.error("没有有效的 IP 地址可写入文件。")

def main():
    test_ip = "8.8.8.8"
    logger.info(f"测试 IP {test_ip} 的国家代码...")
    country = get_country_code(test_ip, "UNKNOWN")
    logger.info(f"测试结果：{test_ip} -> {country}")

    ip_list = fetch_ips()
    if not ip_list:
        logger.error("未抓取到 IP 列表，程序退出。")
        return

    save_ips(ip_list)

if __name__ == "__main__":
    main()
