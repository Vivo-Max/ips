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

# 亚太地区国家/地区代码（不包含 CN）
ASIA_PACIFIC_REGIONS = {
    'JP', 'KR', 'SG', 'TW', 'HK', 'MY', 'TH', 'ID', 'PH',
    'VN', 'IN', 'AU', 'NZ', 'MO', 'BN', 'KH', 'LA', 'MM', 'TL'
}

MAX_NODES = 100

def fetch_csv_data(url: str) -> str:
    """从 URL 获取数据，支持重试"""
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
    """检查是否为有效的 IPv4 地址"""
    return bool(re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", s))

def is_port(s: str) -> bool:
    """检查是否为有效的端口号"""
    try:
        port = int(s)
        return 1 <= port <= 65535
    except ValueError:
        return False

def is_delay(s: str) -> bool:
    """检查是否为延迟值（如 '51 ms' 或 '51'）"""
    return bool(re.match(r"^\d+(\.\d+)?\s*ms$", s)) or s.isdigit()

def parse_csv_and_sort(data: str):
    """通用解析 CSV，支持任意格式"""
    try:
        f = StringIO(data)
        # 检测分隔符
        delimiters = [',', '\t', ';']
        for delimiter in delimiters:
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)
            if len(rows) > 1 and len(rows[0]) > 1:  # 确保有数据且分隔有效
                break
        else:
            logger.error("无法确定CSV分隔符")
            return []

        header = rows[0]
        data_rows = rows[1:]
        logger.info(f"CSV字段数: {len(header)}, 示例行: {data_rows[0] if data_rows else '无数据'}")

        # 推测字段位置
        ip_col = port_col = country_col = delay_col = None
        for i, field in enumerate(header):
            field_lower = field.lower()
            if 'ip' in field_lower or '地址' in field_lower or '国际代码' in field_lower:
                ip_col = i
            elif 'port' in field_lower or '端口' in field_lower:
                port_col = i
            elif 'country' in field_lower or '国家' in field_lower or 'code' in field_lower:
                country_col = i
            elif 'delay' in field_lower or '延迟' in field_lower:
                delay_col = i

        # 如果未找到关键字段，尝试从数据推测
        if not all([ip_col, port_col, country_col]):
            sample_row = data_rows[0] if data_rows else []
            for i, value in enumerate(sample_row):
                if is_ip(value) and ip_col is None:
                    ip_col = i
                elif is_port(value) and port_col is None:
                    port_col = i
                elif len(value.strip()) == 2 and value.strip().upper() in ASIA_PACIFIC_REGIONS and country_col is None:
                    country_col = i
                elif is_delay(value) and delay_col is None:
                    delay_col = i

        if not all([ip_col, port_col, country_col]):
            logger.error("无法推测IP、端口或国家字段位置")
            return []

        logger.info(f"推测字段位置 - IP: {ip_col}, Port: {port_col}, Country: {country_col}, Delay: {delay_col}")

        nodes = []
        for row in data_rows:
            if len(row) <= max(ip_col, port_col, country_col, delay_col or -1):
                continue
            try:
                ip = row[ip_col].strip()
                if not is_ip(ip):
                    continue

                port = row[port_col].strip()
                if not is_port(port):
                    port = "443"  # 默认端口
                port = int(port)

                country = row[country_col].strip().upper()
                if country not in ASIA_PACIFIC_REGIONS:
                    continue

                delay = 9999  # 默认延迟
                if delay_col is not None and row[delay_col].strip():
                    delay_str = row[delay_col].strip()
                    if is_delay(delay_str):
                        delay = float(delay_str.replace(' ms', '')) if 'ms' in delay_str else float(delay_str)

                remark = f"{ip}:{port}#{country}"
                nodes.append((delay, remark))
            except (ValueError, IndexError) as e:
                logger.debug(f"跳过无效行: {row} - {e}")
                continue

        nodes.sor
