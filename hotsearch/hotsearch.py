import requests
from deepseek import DeepSeekAPI
import smtplib
from email.utils import formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule
import time
import json
from datetime import datetime
import os
import markdown2
import sys
import pymysql
# 配置部分
CONFIG = {
    "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY"),
    "email": {
        "sender": os.getenv("EMAIL_SENDER"),
        "receiver": os.getenv("EMAIL_RECEIVER"),
        "password": os.getenv("EMAIL_PASSWORD")
    },
    "data_sources": ["baidu", "weibo",'zhihu'],  # 可扩展的数据源
    "output_dir": "reports" , # 报告存储目录
    "baidu":"百度",
    "weibo":"微博",
    "zhihu":"知乎",
    "mysql": {
        "user": "******",
        "password": "******",
        "host": '0.0.0.0' if sys.platform !='darwin' else '*******',
        "port": 3306,
        "database": "*******"
    }
}

import logging
import os

def setup_logger(name: str, log_file: str, level=logging.INFO) -> logging.Logger:
    """创建一个自定义 logger，带格式，输出到文件和控制台"""

    # 防止重复添加 handler（避免重复输出）
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    # 创建日志目录（如果不存在）
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # 自定义格式
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 文件 handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 添加 handler 到 logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

class HotspotReporter:
    def __init__(self,logger):
        self.ds = DeepSeekAPI(api_key=CONFIG["deepseek_api_key"])
        os.makedirs(CONFIG["output_dir"], exist_ok=True)
        self.logger = logger

    def fetch_hotspots(self, source):
        """从不同平台获取热点数据"""

        if source == "baidu":
            return [{'name':'baidu','data':self._fetch_baidu_hot()}]
        elif source == "weibo":
            return [{'name':'weibo','data':self._fetch_weibo_hot()}]
        else:
            return [{'name':'zhihu','data':self.get_zhihu_hot_list()}]

    def get_zhihu_hot_list(self):
        url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Referer": "https://www.zhihu.com/billboard",
        }
        response = requests.get(url, headers=headers)
        datas = []
        try:
            data = response.json()
            hot_list = data["data"]

            for i, item in enumerate(hot_list, 1):
                temp = {'title': item["target"]["title"], 'url': item["target"]["url"].replace('api.zhihu','zhihu').replace('questions','question'),'source': "zhihu"}
                datas.append(temp)
            return datas[:10]
        except (requests.RequestException, ValueError) as e:
            logger.info("获取知乎热搜失败：", e)
            return []

    def _fetch_baidu_hot(self):
        """获取百度热搜"""
        url = "https://top.baidu.com/api/board?platform=wise&tab=realtime"
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            return [
                       {
                           "source": "baidu",
                           "title": item.get("word"),
                           "url": item.get("url"),

                       }
                       for item in data.get("data", {}).get("cards", [{}])[0].get("content", [])
                   ][:10]

        except Exception as e:
            logger.info(f"获取百度热搜失败: {e}")
            return []

    def _fetch_weibo_hot(self):
        """获取微博热搜"""
        url = "https://weibo.com/ajax/side/hotSearch"
        headers = {"User-Agent": "Mozilla/5.0"}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            return [
                       {
                           "source": "weibo",
                           "title": item.get("word"),
                           "url": f"https://s.weibo.com/weibo?q={item.get('word')}",

                       }
                       for item in data.get("data", {}).get("realtime", [])
                   ][:10]

        except Exception as e:
            logger.info(f"获取微博热搜失败: {e}")
            return []

    def generate_report(self, all_hotspots):
        """生成综合分析报告"""
        if not all_hotspots:
            return "今日无热点数据"

        prompt = self._build_prompt(all_hotspots)

        try:
            response = self.ds.fim_completion(prompt, max_tokens=2500)
            return response
        except Exception as e:
            logger.info(f"DeepSeek分析失败: {e}")
            return "报告生成失败"

    def _build_prompt(self, hotspots):
        """构建分析提示词"""
        hotspots_str = "\n".join(
            f"{idx + 1}. [{item['source']}] {item['title']} (热度: {item.get('hot_score', 'N/A')})"
            for idx, item in enumerate(hotspots)
        )

        return f"""你是一位资深行业分析师，请根据以下热点事件生成一份专业报告：

        今日热点榜单：
        {hotspots_str}

        报告要求：
        1. 选出5-8个最具影响力的事件，优先选择跨平台热点
        2. 对每个事件进行200字左右的深度分析，包括：
           - 事件背景
           - 可能影响
           - 相关方反应
        3. 综合分析行业趋势
        4. 给出可操作的业务建议

        报告格式：
        # {datetime.now().strftime('%Y-%m-%d')} 热点分析报告

        ## 重点事件分析
        ### 1. [事件标题]
        [分析内容]

        ### 2. [事件标题]
        [分析内容]

        ## 综合趋势与建议
        [您的专业分析]
        """
    def save_to_db(self, source):
        data, source_type = source[0]['data'], source[0]['name']
        db_conf = CONFIG["mysql"]
        connection = pymysql.connect(
            host=db_conf["host"],
            port=db_conf["port"],
            user=db_conf["user"],
            password=db_conf["password"],
            database=db_conf["database"],
            charset="utf8mb4"
        )
        try:
            with connection.cursor() as cursor:
                # 删除旧数据
                delete_sql = "DELETE FROM hotsearch WHERE tag = %s"
                cursor.execute(delete_sql, (source_type,))

                # 插入新数据
                insert_sql = "INSERT INTO hotsearch (tag, title, url) VALUES (%s, %s, %s)"
                values = [(source_type, item["title"], item["url"]) for item in data]
                cursor.executemany(insert_sql, values)

            connection.commit()
            self.logger.info(f"{source_type} 数据已保存到 MySQL，共 {len(data)} 条")
        except Exception as e:
            connection.rollback()
            self.logger.error(f"{source_type} 数据保存失败：{e}")
        finally:
            connection.close()
    def save_report(self, report_content):
        """保存报告到本地"""
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"{CONFIG['output_dir']}/{today}_{report_content[0]['name']}_hotspot_report.md"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_content[0]['data'])

        logger.info(f"报告已保存到 {filename}")

    def send_report(self, report_content_md, hot_data, error_info=None):
        """发送 Markdown + HTML 格式的热点报告邮件"""



        # Markdown 转 HTML
        report_html = markdown2.markdown(report_content_md)

        # 构建热搜 HTML 表格部分
        hot_html_parts = ""
        if hot_data:
            subject = f"{CONFIG[hot_data[0]['name']]} 热点分析报告"
            for source in hot_data:
                hot_html_parts += f"<h3>{CONFIG[hot_data[0]['name']]} 热搜</h3>"
                hot_html_parts += """
                <table border="1" cellspacing="0" cellpadding="5" style="border-collapse: collapse; width: 100%;">
                    <tr style="background-color: #f2f2f2;">
                    <th style="text-align:left;">序号</th>
                    <th style="text-align:left;">标题</th>
                    <th style="text-align:left;">链接</th>
                 </tr>
                """
                for idx, item in enumerate(source["data"], 1):
                    hot_html_parts += f"""
                    <tr>
                        <td>{idx}</td>
                        <td>{item.get('title', '')}</td>
                        <td><a href="{item.get('url', '#')}">点击查看</a></td>
                    </tr>
                    """
                hot_html_parts += "</table><br>"
        else:
            subject = f"error 热点分析报告"


        if error_info:
            hot_html_parts += f"""
            <h3 style="color: red;">⚠️ 错误信息</h3>
            <pre>{error_info}</pre>
            """
        hot_name = CONFIG[hot_data[0]['name']]
        # 整体 HTML 模板
        full_html = f"""
        <html>
        <body>
            {report_html}
            <hr>
            {hot_html_parts}
        </body>
        </html>
        """

        # 构建邮件
        msg = MIMEMultipart("alternative")
        #msg["From"] = CONFIG["email"]["sender"]
        msg["From"] = formataddr(("小刚的日报 📬", CONFIG["email"]["sender"]))
        msg["To"] = CONFIG["email"]["receiver"]
        msg["Subject"] = subject
        msg.attach(MIMEText(full_html, "html"))

        # 发送邮件
        try:
            with smtplib.SMTP_SSL("smtp.163.com", 465) as server:
                server.login(CONFIG["email"]["receiver"], CONFIG["email"]["password"])
                server.sendmail(
                    CONFIG["email"]["sender"],
                    CONFIG["email"]["receiver"],
                    msg.as_string()
                )
            logger.info("✅ 邮件发送成功")
        except Exception as e:
            logger.info(f"❌ 邮件发送失败: {e}")


def main_job(logger):
    logger.info(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 开始执行热点报告任务...")
    reporter = HotspotReporter(logger)
    all_hotspots = []
    for source in CONFIG["data_sources"]:
        hotspots = reporter.fetch_hotspots(source)
        all_hotspots.append(hotspots)
        reporter.save_to_db(hotspots)
        logger.info(f"从 {source} 获取到 {len(hotspots[0]['data'])} 条热点")
    current_hour = datetime.now().hour
    current_minute = datetime.now().minute
    if current_hour == 8 and current_minute == 00 and all_hotspots:
        try:
            for hotspot in all_hotspots:
                report = reporter.generate_report(hotspot[0]["data"])
                # reporter.save_report(hotspot)
                #report = 'test'
                reporter.send_report(report, hot_data=hotspot)
                # time.sleep(5)
        except (requests.RequestException, ValueError) as e:
            reporter.send_report('',[],error_info=str(e))

    else:
        logger.info("stop doing")
        #reporter.send_report('',[],error_info='dont has information')

    logger.info("任务执行完成")


if __name__ == "__main__":
    # 首次立即执行
    #  */10 * * * * /home/hotdog/hotsearch.sh >> /home/hotdog/hotsearch.log 2>&1 crontab 设置定时
    logger = setup_logger("hotsearch", "logs/hotsearch.log")
    main_job(logger)


