import random
from locust import HttpUser, task, between
from bs4 import BeautifulSoup
import re


class WebsiteUser(HttpUser):
    host = "http://127.0.0.1:12000"
    wait_time = between(1, 5)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.csrf_token = ""
        self.cookies = {}

    def get_csrf_token(self):
        # 获取登录页面的CSRF令牌
        response = self.client.get("/login")
        soup = BeautifulSoup(response.text, "html.parser")
        csrf_input = soup.find("input", {"name": "csrf_token"})
        if csrf_input:
            self.csrf_token = csrf_input["value"]
            return True
        return False

    def login(self):
        if not self.csrf_token and not self.get_csrf_token():
            return False

        response = self.client.post(
            "/login",
            {
                "username": "testuser",
                "password": "testuserpassword",
                "csrf_token": self.csrf_token,
            },
            allow_redirects=False,
        )

        if response.status_code == 302:
            self.cookies = response.cookies
            # print("登录成功")
            return True

        print(f"登录失败，状态码: {response.status_code}")
        return False

    def on_start(self):
        if not self.login():
            self.environment.runner.quit()
            raise Exception("无法登录，停止测试")

    @task
    def test_search(self):
        if not self.cookies:
            if not self.login():
                return

        keyword = "nature"  # 测试关键词
        # response = self.client.post(
        #     "/search/",
        #     {
        #         "tags": keyword,
        #         "exact_match": "on",
        #         "csrf_token": self.csrf_token,  # 搜索页面可能也需要CSRF
        #     },
        #     cookies=self.cookies,
        # )
        response = self.client.get(
            "/gallery-music/",
            params={
                "page": random.randint(1, 10),
                # "csrf_token": self.csrf_token,  # 搜索页面可能也需要CSRF
            },
            cookies=self.cookies,
        )

        if response.status_code != 200:
            print(f"搜索失败: {response.status_code}")
