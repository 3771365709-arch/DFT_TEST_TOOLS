环境变量是由操作系统提供给程序读取的“配置项”。它的作用是把不适合写死在代码里的参数放到代码外部，例如服务器地址、Token、输入目录、运行模式等。

一、对 tools_for_LB3 有什么用
目前 upload_to_server.py 中有写死的配置：


SERVER_URL = 'http://192.168.1.100:8000'
MAX_RETRY = 3
如果代码直接上传到 GitHub，服务器地址会暴露，而且不同用户每次都要修改源码。

更好的做法是：


代码：从环境变量读取配置
电脑：保存每个人自己的配置
GitHub：只保存代码，不保存服务器地址和 Token
例如：


LB3_SERVER_URL
LB3_UPLOAD_TOKEN
LB3_ROOT
LB3_MAX_RETRY
二、Windows PowerShell 中设置环境变量
1. 只对当前 PowerShell 窗口有效

$env:LB3_SERVER_URL = "https://your-server.example.com"
$env:LB3_UPLOAD_TOKEN = "your-token"
检查是否设置成功：


$env:LB3_SERVER_URL
$env:LB3_UPLOAD_TOKEN
然后在同一个 PowerShell 窗口中运行：


python upload_to_server.py
关闭这个窗口后，这些变量就失效。

2. 永久保存到当前用户

[Environment]::SetEnvironmentVariable(
    "LB3_SERVER_URL",
    "https://your-server.example.com",
    "User"
)

[Environment]::SetEnvironmentVariable(
    "LB3_UPLOAD_TOKEN",
    "your-token",
    "User"
)
设置后需要：

重新打开 PowerShell；
或重启 VS Code；
再检查：

$env:LB3_SERVER_URL
删除用户级环境变量：


[Environment]::SetEnvironmentVariable("LB3_SERVER_URL", $null, "User")
[Environment]::SetEnvironmentVariable("LB3_UPLOAD_TOKEN", $null, "User")
3. 临时取消当前窗口中的变量

Remove-Item Env:LB3_SERVER_URL
Remove-Item Env:LB3_UPLOAD_TOKEN
三、Linux/macOS 中设置方法
当前终端有效：


export LB3_SERVER_URL="https://your-server.example.com"
export LB3_UPLOAD_TOKEN="your-token"
python3 upload_to_server.py
永久保存，可以写入：


~/.bashrc
或：


~/.zshrc
例如：


export LB3_SERVER_URL="https://your-server.example.com"
export LB3_UPLOAD_TOKEN="your-token"
然后加载：


source ~/.bashrc
四、当前工具还需要读取环境变量
仅仅设置环境变量，当前版本的 upload_to_server.py 不会自动使用它，因为它目前直接读取代码中的常量。

需要将：


SERVER_URL = 'http://192.168.1.100:8000'
LB3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_RETRY = 3
RETRY_SLEEP = 2
改成：


SERVER_URL = os.environ.get(
    'LB3_SERVER_URL',
    'http://192.168.1.100:8000'
)

LB3_ROOT = os.environ.get(
    'LB3_ROOT',
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

MAX_RETRY = int(os.environ.get('LB3_MAX_RETRY', '3'))
RETRY_SLEEP = float(os.environ.get('LB3_RETRY_SLEEP', '2'))
UPLOAD_TOKEN = os.environ.get('LB3_UPLOAD_TOKEN', '')
这样就实现了：

设置环境变量时，使用外部配置；
没有设置时，继续使用默认值；
旧的运行方式不会立即失效。
客户端发送 Token：


if UPLOAD_TOKEN:
    req.add_header('Authorization', 'Bearer ' + UPLOAD_TOKEN)
对应的服务端读取 Token：


UPLOAD_TOKEN = os.environ.get('LB3_UPLOAD_TOKEN', '')
在 do_POST() 中验证：


auth = self.headers.get('Authorization', '')
if not UPLOAD_TOKEN or auth != 'Bearer ' + UPLOAD_TOKEN:
    self._send(401, 'Unauthorized')
    return
客户端和服务端必须设置相同的 Token。

五、推荐的运行方式
PowerShell 中：


$env:LB3_SERVER_URL = "https://your-server.example.com"
$env:LB3_UPLOAD_TOKEN = "replace-with-a-long-random-token"
$env:LB3_MAX_RETRY = "5"

cd "C:\Users\Administrator\Desktop\LB3_OUTPUT\tools_for_LB3"
python upload_to_server.py all
也可以不永久保存，只在本次运行前设置。

六、使用 .env 文件是否更方便
可以使用 .env 文件，例如：


LB3_SERVER_URL=https://your-server.example.com
LB3_UPLOAD_TOKEN=replace-with-your-token
LB3_MAX_RETRY=5
然后用 python-dotenv 加载：


pip install python-dotenv
代码中：


from dotenv import load_dotenv

load_dotenv()
但是要注意：.env 可能包含 Token，必须加入 .gitignore：


.env
*.env
对于当前这个小工具，我更推荐先使用系统环境变量，因为：

不需要增加依赖；
不会意外把 .env 上传到 GitHub；
Windows 和 Linux 都支持；
更适合服务器和 CI 环境。
七、环境变量和普通配置文件的区别
方式	适合存放	特点
代码常量	默认值、固定规则	简单，但修改和保密较差
JSON/YAML 配置	列名、单位、分类规则	结构清晰，适合项目配置
环境变量	Token、服务器地址、路径	不进入代码仓库，适合部署配置
.env 文件	本地开发配置	方便，但必须加入 .gitignore
建议这样分工：


lb3tools_project.py / config.json
    存：列名、单位、结果词、正则、标称条件

环境变量
    存：服务器地址、Token、个人路径、重试参数

代码
    存：通用分析逻辑
八、安全注意事项
环境变量比把 Token 写进代码安全，但它不是绝对保密机制：

当前用户下的其他程序可能读取它；
子进程通常会继承它；
不要在日志中打印 Token；
不要把 $env:LB3_UPLOAD_TOKEN 的值复制到 GitHub Issue；
不要将 .env 提交到仓库；
服务器 Token 建议使用较长的随机字符串并定期更换。
一句话总结：

环境变量可以让 tools_for_LB3 的代码和运行环境配置分离；对于这个项目，最适合先用它保存上传服务器地址、上传 Token、数据根目录和重试参数，而列名、单位和测试规则仍放在项目配置文件中。