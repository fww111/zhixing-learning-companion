from __future__ import annotations

from app.models.profile import StudentProfile


class TutorAgent:
    name = "智能辅导Agent"

    def answer(self, profile: StudentProfile, question: str, topic: str) -> str:
        return (
            f"简短结论：{topic}可以先从直观图像理解。\n\n"
            f"图解类比：把损失函数看作山谷，参数沿下降方向移动。\n\n"
            f"关键步骤：计算预测、计算损失、求梯度、按学习率更新参数。\n\n"
            f"推荐复习：先看思维导图，再运行代码案例。\n\n"
            f"检查题：学习率过大会出现什么现象？"
        )
