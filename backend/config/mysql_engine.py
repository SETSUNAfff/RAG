from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from dotenv import load_dotenv
import os

load_dotenv(override=True)
ASYNC_DATABASE_URL = os.getenv('ASYNC_DATABASE_URL')

# 创建异步引擎
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=True,       #可选：输出SQL日志
    pool_size = 10,  #设置连接池中保持的持久连接数
    max_overflow = 20 #设置连接处允许创建的超过连接池大小连接数
)

#创建会话工厂
async_session = async_sessionmaker(
    bind=async_engine, # 绑定数据库引擎
    class_=AsyncSession,  # 指定会话类
    expire_on_commit=False  # 会话对象不过期，不重新查询数据
)

#创建依赖项，用于获取数据库会话
async def get_db():
    async with async_session() as db:
        try:
            yield db   # 返回数据库会话
            await db.commit() # 提交事务
        except Exception:
            await db.rollback() # 发生错误时回滚事务
            raise
