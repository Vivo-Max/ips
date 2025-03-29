name: Update Cloudflare IPs

on:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:

jobs:
  update-ips:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.x"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4 geoip2 selenium

      - name: Install Chrome and ChromeDriver
        run: |
          sudo apt-get update
          sudo apt-get install -y google-chrome-stable
          CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
          wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION})/chromedriver_linux64.zip"
          unzip /tmp/chromedriver.zip -d /usr/local/bin/
          chmod +x /usr/local/bin/chromedriver

      - name: Run script to fetch IPs
        run: python fetch_cloudflare_ips.py

      - name: Commit and push changes
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git add ip.txt
          git diff --staged --quiet || git commit -m "Update Cloudflare IPs - $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
          git push
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
