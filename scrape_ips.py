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

MAX_NODES = 100

def fetch_csv_data():
    try:
        logger.info(f"正在从 {CSV_URL} 获取数据...")
        response = requests.get(CSV_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        logger.info("成功获取CSV数据")
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(f"获取CSV数据失败: {e}")
        return None

def parse_csv_and_sort(data):
    try:
        f = StringIO(data)
        reader = csv.DictReader(f, delimiter='\t')
        
        # 调试：打印字段名
        logger.info(f"CSV字段名: {reader.fieldnames}")
        
        nodes = []
        for row in reader:
            try:
                # 调试：打印每行数据
                logger.debug(f"处理行: {row}")
                
                ip = row['国际代码'].strip()
                # 假设端口字段名为 '端口'，如果不同请根据日志调整
                port = row.get('端口', '443').strip()  # 默认443，如果字段缺失
                country = row['国家'].strip().upper()
                delay_str = row['网络延迟'].strip()
                delay = float(delay_str.replace(' ms', ''))

                if country in ASIA_PACIFIC_REGIONS:
                    remark = f"{ip}:{port}#{country}"
                    nodes.append((delay, remark))
            except KeyError as e:
                logger.error(f"字段缺失: {e}")
                continue
            except ValueError as e:
                logger.error(f"数据格式错误: {e}")
                continue

        nodes.sort(key=lambda x: x[0])
        return [node[1] for node in nodes[:MAX_NODES]]

    except Exception as e:
        logger.error(f"解析CSV失败: {e}")
        return []

def save_ips(ip_list):
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
