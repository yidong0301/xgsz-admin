# 真实推理示例镜像：构建期在真实数据集上训练模型，运行时在 K8s 里做真实推理
#
# 说明：本机 kind 集群无外网，基础的 python:3.8-slim 拉不下来，
# 因此复用本地已有的 wdxmgz-backend:latest（同为 python:3.8-slim 系）。
# 有镜像仓库时可直接改成：FROM python:3.8-slim
FROM wdxmgz-backend:latest

WORKDIR /infer
COPY train.py infer.py /infer/

# 真实依赖（CPU）：numpy / scikit-learn / joblib 走国内镜像
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
        numpy==1.24.4 scikit-learn==1.3.2 joblib==1.3.2 \
    && python /infer/train.py --out /models

ENV PYTHONUNBUFFERED=1 MODEL_DIR=/models PORT=8080
EXPOSE 8080

# 默认在线服务；批量推理任务用 command/args 覆盖为 --mode batch
CMD ["python", "/infer/infer.py", "--mode", "serve", "--port", "8080"]
