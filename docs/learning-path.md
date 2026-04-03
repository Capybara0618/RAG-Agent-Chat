# 小白学习路线

这份文档是给初学者准备的。目标不是让你一上来就看懂每一行代码，而是先顺着一次完整请求，把这个系统的主链路走明白，并能说清每个核心模块在做什么。

## 学习目标

在深入细节之前，你应该先能回答这三个问题：

1. 这个项目解决的是什么问题？
2. 用户提一个问题以后，代码先走到哪里，再走到哪里？
3. 为什么它不只是一个普通聊天机器人？

如果你已经能清楚回答这三个问题，说明你的第一层基础就已经打好了。

## 推荐学习顺序

### 第 1 步：先看懂项目故事

先读这两个文件：

- [README.md](D:/Code/RAG+Agent项目/README.md)
- [architecture.md](D:/Code/RAG+Agent项目/docs/architecture.md)

读完以后，你至少要能用自己的话复述这条链路：

`知识上传 -> 检索 -> Agent 工作流 -> 引用校验 -> trace -> 评测`

这一步不要纠结代码细节，只要看懂项目是在做什么。

### 第 2 步：看后端总入口

接着读：

- [main.py](D:/Code/RAG+Agent项目/app/main.py)

这一阶段只关注三个问题：

- 这里创建了哪些服务？
- 这里注册了哪些路由？
- 应用启动时做了什么？

你暂时不需要理解每个类的内部实现，只要把 `main.py` 当成整个系统的“组装中心”来看就够了。

### 第 3 步：顺着一次用户提问追代码

按下面顺序读：

- [chat.py](D:/Code/RAG+Agent项目/app/api/routes/chat.py)
- [service.py](D:/Code/RAG+Agent项目/app/services/agent/service.py)
- [workflow.py](D:/Code/RAG+Agent项目/app/services/agent/workflow.py)

这是整个项目里最重要的一段学习内容。

你要真正看懂这条路径：

1. API 收到一个问题
2. 系统创建 session 和 trace
3. 问题进入 5 节点工作流
4. 最终返回 `answer`、`citations`、`confidence` 和 `trace_id`

读这些文件时，遇到看不懂的语法先不要卡住，持续问自己三个问题：

- 输入是什么？
- 输出是什么？
- 它是被谁调用的？

## 怎么理解 Agent 工作流

在 [workflow.py](D:/Code/RAG+Agent项目/app/services/agent/workflow.py) 里，这个项目用了 5 个节点：

1. `Intent Router`
2. `Retrieval Planner`
3. `Tool Executor`
4. `Answer Composer`
5. `Citation Verifier`

一开始你不需要深入学习 LangGraph，只要先把每个节点翻译成大白话：

- `Intent Router`：先判断这是什么类型的问题
- `Retrieval Planner`：决定应该怎么检索
- `Tool Executor`：真正去拿知识内容
- `Answer Composer`：根据证据组织答案
- `Citation Verifier`：检查答案是不是有证据支撑

如果你已经能用自己的话讲明白这 5 个节点分别负责什么，那第一阶段就很不错了。

## 再学 RAG 核心

当主请求链路已经清楚以后，再看：

- [service.py](D:/Code/RAG+Agent项目/app/services/retrieval/service.py)
- [embeddings.py](D:/Code/RAG+Agent项目/app/services/retrieval/embeddings.py)

这个阶段先只理解 4 个词：

- `query rewrite`
- `retrieve`
- `rerank`
- `compress context`

你要带走的核心理解是：

- 系统会先改写问题，让检索更容易命中
- 然后从知识库里拿候选 chunk
- 再做一次重排，把更有价值的结果留到前面
- 最后把上下文压缩后再交给答案生成

你现在不是在学高级向量数据库理论，而是在学“这个项目为什么能给出带依据的答案”。

## 再看知识是怎么进系统的

然后看：

- [service.py](D:/Code/RAG+Agent项目/app/services/ingestion/service.py)
- [connectors.py](D:/Code/RAG+Agent项目/app/services/ingestion/connectors.py)
- [chunking.py](D:/Code/RAG+Agent项目/app/services/ingestion/chunking.py)

你要看懂三件事：

- 文件是怎么读进来的
- 文本是怎么被切块的
- chunk 是怎么变成可检索数据的

你可以把这一部分理解成一句话：原始知识是怎么被加工成“可搜索知识”的。

## 数据模型和前端最后再看

只有在主链路已经清楚之后，再去读：

- [entities.py](D:/Code/RAG+Agent项目/app/models/entities.py)
- [app.py](D:/Code/RAG+Agent项目/frontend/app.py)

看数据模型时，第一轮先只认识下面这 6 个对象：

- `Document`
- `Chunk`
- `ChatSession`
- `ChatMessage`
- `TraceRecord`
- `EvalRun`

不用一开始就背所有字段，只要知道它们为什么存在就够了。

## 最适合你的阅读方法

每读一个文件，只做三件事：

1. 写一句话：“这个文件负责什么”
2. 写一句话：“它的输入是什么，输出是什么”
3. 写一句话：“它会被谁调用”

第一遍不要逐行硬读。

对这个仓库来说，最适合小白的方法就是：

- 顺着一次请求走
- 每看完一个文件写一句总结
- 遇到难点先跳过去，第二轮再回来看

## 练习数据

先用这些样例文件理解业务内容，不要一开始自己造场景：

- [sample_handbook.md](D:/Code/RAG+Agent项目/data/sample_handbook.md)
- [sample_policy.md](D:/Code/RAG+Agent项目/data/sample_policy.md)
- [sample_faq.csv](D:/Code/RAG+Agent项目/data/sample_faq.csv)

这些文件能帮你把“代码行为”和“真实知识内容”对应起来。

## 练习问题

学习时优先用这 3 个问题来追主流程：

1. `What should a new employee complete before receiving production access?`
2. `Compare onboarding requirements with remote access requirements.`
3. `What is the first step in the incident workflow?`

对每个问题，你都试着回答：

- 是哪个 route 接收了它？
- 是哪个 service 处理了它？
- 经过了哪些 workflow 节点？
- citations 是从哪里来的？

## 把测试当成地图看

在主流程已经看明白之后，再去读这些测试：

- [test_chat_flow.py](D:/Code/RAG+Agent项目/tests/test_chat_flow.py)
- [test_permissions.py](D:/Code/RAG+Agent项目/tests/test_permissions.py)
- [test_evaluation.py](D:/Code/RAG+Agent项目/tests/test_evaluation.py)

测试的价值在于：它会告诉你系统“应该怎么工作”，而不要求你先看懂所有实现细节。

## 第一阶段完成标准

如果你已经能讲清楚下面这些点，就说明第一阶段完成得不错：

- 文档是怎么进入系统的
- 用户问题是怎么变成检索上下文的
- Agent 工作流是怎么生成有依据的回答的
- 为什么系统要保存 `trace_id`
- 为什么这个项目比普通聊天机器人 demo 更强

这对初学者来说已经是一个很扎实的阶段成果了。

## 第一轮不要先做什么

第一轮先不要从这些地方开始：

- SQLAlchemy 全部细节
- FastAPI 全部细节
- LangGraph 内部机制
- 每个模型的全部字段
- 前端细节代码

这些都适合第二轮再补。

第一轮最重要的是先抓住项目主线和请求主流程。

## 下一步建议

等你走完这份路线，最适合的下一步就是做一个 7 天学习计划。每天只安排：

- 少量文件
- 3 到 5 个关键问题
- 一个简短总结练习
- 一个小型 tracing 练习

这是从“小白看不懂”走到“我能在面试里讲清楚这个项目”的最快路径。