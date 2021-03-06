from urllib import request
import json
import ssl

Ding_Hook_Url = "https://oapi.dingtalk.com/robot/send?access_token=token"


class DingHook(object):

    def post_request(self, data):

        ssl._create_default_https_context = ssl._create_unverified_context

        headers = {"Content-Type": "application/json"}

        req = request.Request(url=Ding_Hook_Url, headers=headers)
        req.get_method = lambda: "POST"
        http_res = request.urlopen(req, bytes(data, encoding="UTF-8"))
        content = http_res.read()
        http_res.close()
        return content

    def post_qrCode(self, title="", text="", picurl="", messageurl=""):
        """构建数据"""
        print("构建钉钉消息数据")
        data = dict()
        data["msgtype"] = "markdown"
        data["markdown"] = {}
        data["markdown"]["title"] = title
        data["markdown"]["text"] = text
  
        data = json.dumps(data)
        content = self.post_request(data)
        print("钉钉消息发送成功")

        return content


if __name__ == '__main__':
    dh = DingHook()
    dh.post_qrCode()


