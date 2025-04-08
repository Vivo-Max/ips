import requests
import csv
import logging
from io import StringIO

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# CSV 数据源
CSV_URL = "https://bihai.cf/CFIP/CUCC/standard.csv"
OUTPUT_FILE = "ip.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

# 亚太地区国家/地区代码（不包含CN）
ASIA_PACIFIC_REGIONS = {
    'JP', 'KR', 'SG', 'TW', 'HK', 'MY', 'TH', 'ID', 'PH',
    'VN', 'IN', 'AU', 'NZ', 'MO', 'BN', 'KH', 'LA', 'MM', 'TL'
}

MAX_NODES = 100  # 获取前100个节点

def fetch_csv_data():
    """从CSV URL获取数据"""
    try:
        logger.info(f"正在从 {CSV_URL} 获取数据...")
        response = requests.get(CSV_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"获取CSV数据失败: {e}")
        return None

def parse_csv_and_sort(data):
    """解析CSV并按延迟排序，返回亚太地区节点（不含CN）"""
    try:
        f = StringIO(data)
        reader = csv.DictReader(f, delimiter='\t')  # 假设CSV以制表符分隔
        
        nodes = []
        for row in reader:
            try:
                ip = row['国际代码'].strip()
                port = row['443'].strip()  # 假设端口字段名为 '443'
                country = row['国家'].strip().upper()
                delay_str = row['网络延迟'].strip()
                delay = float(delay_str.replace(' ms', ''))

                if country in ASIA_PACIFIC_REGIONS:
                    remark = f"{ip}:{port}#{country}"
                    nodes.append((delay, remark))
            except (ValueError, KeyError) as e:
                continue

        # 按延迟排序并取前MAX_NODES个
        nodes.sort(key=lambda x: x[0])  # 按延迟升序排序
        return [node[1] for node in nodes[:MAX_NODES]]

    except Exception as e:
        logger.error(f"解析CSV失败: {e}")
        return []

def save_ips(ip_list):
    """保存IP列表到文件"""
    with open(OUTPUT_FILE, "w") as f:
        for ip in ip_list:
            f.write(f"{ip}\n")
    logger.info(f"已保存 {len(ip_list)} 个节点到 {OUTPUT_FILE}")

if __name__ == "__main__":
    csv_data = fetch_csv_data()
    if csv_data:
        ip_list = parse_csv_and_sort(csv_data)
        if ip_list:
            save_ips(ip_list)
        else:
            logger.error("未解析到有效的亚太地区节点！")
    else:
        logger.error("未能获取CSV数据！")
