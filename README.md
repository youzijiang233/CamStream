## 📷 CamStream

**CamStream** 是一个基于 Flask 开发的轻量级 USB 摄像头直播系统，支持用户注册/登录、管理面板、自定义摄像头参数设置、实时视频流预览等功能。可用于校园科研、宿舍监控、项目展示等场景。

***

### 🚀 功能特点

* 🔒 用户系统（注册 / 登录 / 权限管理）

* 📺 实时 USB 摄像头视频流预览

* ⚙️ 管理后台：支持摄像头分辨率、帧率、编码方式设置

* 🧩 支持邀请码注册与用户管理

* 📊 带宽监测与实时帧率显示

* 🐍 使用 Python + Flask + OpenCV 开发

***


### 🛠️ 安装与运行

#### 1. 克隆项目

```bash
git clone https://github.com/yourusername/CamStream.git
cd CamStream
```

#### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> 依赖包包括：
>
> * Flask
>
> * Flask-Login
>
> * Flask-WTF
>
> * OpenCV (`opencv-python`)
>
> * Werkzeug
>
> * numpy

#### 3. 运行程序

```
python app.py
```

默认监听：`http://localhost:5000`

***

### 🔐 默认管理员账号

* 用户名：`admin`

* 密码：`123456`

***

### ⚙️ 可自定义参数

* 摄像头分辨率（宽 / 高）

* 帧率 FPS（推荐：15）

* 编码方式（JPEG / H.264，注意浏览器兼容性）

***

### 📁 项目结构

```
CamStream/
├── app.py                 # 主程序入口
├── templates/             # HTML 模板目录
│   ├── login.html
│   ├── register.html
│   ├── admin.html
│   └── stream.html
└── users.db               # 自动生成的数据库
```

***

### 📌 注意事项

* H.264 视频编码不能直接在浏览器中预览，请使用 JPEG 编码。

* 项目首次运行会自动初始化数据库。

* 如果摄像头无法打开，请确认设备是否占用、驱动是否正确。

* 点击pack_exe.bat，自动生成.exe可执行文件

