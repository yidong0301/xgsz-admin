FROM python:3.8-slim

WORKDIR /app

# 系统依赖（gcc 用于编译部分包）
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .
# Linux 上重新启用 ansible（Windows 因符号链接问题被注释掉）
RUN sed -i 's/^# ansible==/ansible==/' requirements.txt \
    && pip install --no-cache-dir pip==23.0.1 \
    && pip install --no-cache-dir -r requirements.txt

# 复制项目
COPY . .

EXPOSE 8000

CMD ["daphne", "xgsz_admin.asgi:application", "-b", "0.0.0.0", "-p", "8000"]
