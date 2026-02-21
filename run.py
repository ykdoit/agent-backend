"""
Enterprise Office Agent - 启动脚本
"""
import os
import sys
import uvicorn
from loguru import logger

# 配置详细的日志输出
logger.remove()  # 移除默认配置
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG",
    enqueue=True
)


def run_studio():
    """启动 AgentScope Studio"""
    logger.info("Starting AgentScope Studio...")
    os.system("as_studio --host 0.0.0.0 --port 5000")


def run_api():
    """启动 FastAPI 服务"""
    logger.info("Starting Enterprise Office Agent API...")
    logger.info("日志级别已设置为 DEBUG，将显示详细执行信息")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8088,
        reload=True,
        log_level="debug"
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "studio":
        run_studio()
    else:
        run_api()
