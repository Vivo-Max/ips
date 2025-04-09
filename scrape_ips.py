import requests
import csv
import logging
import re
from io import StringIO
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

CSV_URL = "https://bihai.cf/CFIP/CUCC/standard.csv"
OUTPUT_FILE = "ip.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

ASIA_PACIFIC_REGIONS = {
    'JP', 'KR', 'SG', 'TW', 'HK', 'MY', 'TH', 'ID', 'PH',
    'VN', 'IN', 'AU', 'NZ', 'MO', 'BN', 'KH', 'LA', 'MM', 'TL'
}

# 添加中文国家名到代码的映射
COUNTRY_MAPPING = {
    '台湾': 'TW', '日本': 'JP', '韩国': 'KR', '新加坡': 'SG', '香港': 'HK',
    '马来西亚': 'MY', '泰国': 'TH', '印度尼西亚': 'ID', '菲律宾': 'PH',
    '越南': 'VN', '印度': 'IN', '澳大利亚': 'AU', '新西兰': 'NZ',
    '美国': 'US'
}

MAX_NODES = 100

def fetch_csv_data(url: str) -> str:
    try:
        logger.info(f"正在从 {url} 获取数据...")
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        logger.info("成功获取CSV数据")
        return response.text
    except requests.RequestException as e:
        logger.error(f"获取CSV数据失败: {e}")
        return None

def is_ip(s: str) -> bool:
    return bool(re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", s))

def is_port(s: str) -> bool:
    try:
        port = int(s)
        return 1 <= port <= 65535
    except ValueError:
        return False

def is_delay(s: str) -> bool:
    return bool(re.match(r"^\d+(\.\d+)?\s*ms$", s)) or s.isdigit()

def parse_csv_and_sort(data: str):
    try:
        f = StringIO(data)
        delimiters = [',', '\t', ';']
        for delimiter in delimiters:
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)
            if len(rows) > 1 and len(rows[0]) > 1:
                break
        else:
            logger.error("无法确定CSV分隔符")
            return []

        header = rows[0]
        data_rows = rows[1:]
        logger.info(f"CSV字段数: {len(header)}, 示例行: {data_rows[0] if data_rows else '无数据'}")

        # 固定字段位置，基于示例数据调整
        ip_col = 0      # IP 地址
        port_col = 1    # 端口
        country_col = 5 # 国家代码 (TW, JP 等)
        delay_col = 8   # 延迟

        logger.info(f"最终字段位置 - IP: {ip_col}, Port: {port_col}, Country: {country_col}, Delay: {delay_col}")

        asia_pacific_nodes = []  # 亚太地区节点
        us_nodes = []           # 美国节点

        for row in data_rows:
            if len(row) <= max(ip_col, port_col, country_col, delay_col or -1):
                continue
            try:
                ip = row[ip_col].strip()
                if not is_ip(ip):
                    logger.debug(f"无效 IP: {ip}")
                    continue

                port = row[port_col].strip()
                if not is_port(port):
                    port = "443"
                port = int(port)

                # 处理国家字段，支持中文映射
                country_raw = row[country_col].strip()
                country = COUNTRY_MAPPING.get(country_raw, country_raw.upper())

                delay = 9999
                if delay_col is not None and row[delay_col].strip():
                    delay_str = row[delay_col].strip()
                    if is_delay(delay_str):
                        delay = float(delay_str.replace(' ms', '')) if 'ms' in delay_str else float(delay_str)

                remark = f"{ip}:{port}#{country}"
                if country in ASIA_PACIFIC_REGIONS:
                    asia_pacific_nodes.append((delay, remark))
                elif country == 'US':
                    us_nodes.append((delay, remark))

            except (ValueError, IndexError) as e:
                logger.debug(f"跳过无效行: {row} - {e}")
                continue

        # 按延迟排序
        asia_pacific_nodes.sort(key=lambda x: x[0])
        us_nodes.sort(key=lambda x: x[0])

        # 优先选取亚太节点，最多 MAX_NODES 个
        result_nodes = asia_pacific_nodes[:MAX_NODES]

        # 如果亚太节点不足 MAX_NODES，补齐美国节点
        if len(result_nodes) < MAX_NODES:
            remaining_slots = MAX_NODES - len(result_nodes)
            result_nodes.extend(us_nodes[:remaining_slots])

        logger.info(f"亚太节点数: {len(asia_pacific_nodes)}, 补齐美国节点数: {len(result_nodes) - len(asia_pacific_nodes)}")
        return [node[1] for node in result_nodes]

    except Exception as e:
        logger.error(f"解析CSV失败: {e}")
        return []

def save_ips(ip_list):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ip in ip_list:
            f.write(f"{ip}\n")
    logger.info(f"已保存 {len(ip_list)} 个节点到 {OUTPUT_FILE}")

if __name_
