# Agent 应用工程师面试准备手册

这份文档基于你当前简历和本仓库项目整理，目标岗位是：

- `Agent 应用工程师`
- `AI 应用工程师`
- `LLM 应用开发工程师`

文档目标不是让你死背所有八股，而是让你做到三件事：

1. 能把自己的经历讲顺。
2. 能把项目里的技术选择讲清楚。
3. 面对底层追问时，至少能答到“机制 + trade-off”这一层。

---

## 1. 总体准备策略

你的简历不能平均用力，建议按下面的比例准备：

- `40%`：`AI Content Ops Agent Platform`
- `20%`：天津行健科技 `Django + RAG + Docker + 测试` 实习
- `15%`：Python / FastAPI / SQLAlchemy / Redis / Vue3 八股
- `15%`：LLM / Agent / LangChain / LiteLLM / RAG
- `10%`：焊缝检测、多模态项目、量化实习、科研论文

你的面试核心思路应该是：

- 先用项目证明你能做事。
- 再用八股证明你理解机制。
- 最后用细节证明你不是在堆名词。

一句话定位建议：

`我是计算机硕士，前期做过多模态算法和工程落地，后面逐步转向 AI 应用和 Agent 系统开发，当前更想做的是把大模型能力工程化，做成可编排、可调用、可持久化、可测试的应用系统。`

---

## 2. 简历里的主线怎么讲

你的简历看起来跨度比较大，面试官可能会觉得你经历分散，所以你需要主动帮他总结主线。

推荐主线：

`算法基础 -> 工程实现 -> AI 应用落地 -> Agent 应用方向`

口语化解释：

`我前期主要做的是多模态检测和深度学习算法，训练、数据、模型调优这些我做得比较多。后面在实习里开始接触 Django、RAG、测试和部署，逐步从算法转向 AI 应用开发。最近这个 Agent 项目是我有意识做的方向性项目，我想把之前的模型理解、后端开发和产品闭环结合起来，所以我现在更希望做 Agent 应用工程师。`

---

## 3. 自我介绍模板

### 3.1 30 秒版本

`我目前是河北科技大学计算机硕士，前期主要做多模态焊缝质量检测相关研究，积累了数据处理、模型训练和算法调优经验。后面在实习和个人项目里逐步转向 AI 应用开发，做过 Django + RAG 系统，也独立做了一个基于 FastAPI、Vue3、LiteLLM 和 LangChain 的 Agent 应用原型。现在我更想做的是把大模型能力工程化，做 Agent 应用和 AI 产品落地。`

### 3.2 1 分钟版本

`我目前是河北科技大学计算机科学与技术硕士，研究方向偏多模态数据融合和质量检测，做过点云分类、缺陷检测和多模态融合算法，所以我的算法基础和实验能力比较扎实。除了科研，我也比较主动往工程方向走，在天津行健的实习里做过 Django 系统开发、RAG 知识库构建、测试和 Docker 部署。最近我自己独立做了一个 AI Content Ops Agent Platform，后端用 FastAPI，前端用 Vue3，模型层用 LiteLLM 做多 provider 路由，做了 4 阶段 Workflow Agent 和支持 tool calling 的 Chat Agent，并把 thread、message、tool events、jobs 都做了持久化。我现在想找的岗位是 Agent 应用工程师，因为我对把 LLM 能力落成完整应用系统这件事更感兴趣。`

### 3.3 3 分钟版本

`我本科和硕士都是计算机背景，硕士期间主要做的是焊缝质量检测相关研究，参与过点云分类、点云缺陷检测和多模态视频电信号融合项目，这一段让我在数据处理、模型训练、实验设计和问题定位方面打下了基础。`

`后面我开始更关注 AI 技术的应用落地。在天津行健的实习中，我参与了金融领域的 AI 应用开发，做了 Django 前后端开发、RAG 知识库构建、文档分块和测试工作，也接触了 Docker 部署和公网访问配置。那段经历让我开始真正理解，一个 AI 系统不仅是模型调用，还包括接口、状态管理、检索、测试和部署。`

`最近我独立做了一个 Agent 应用项目，叫 AI Content Ops Agent Platform。这个项目不是简单的聊天页面，而是一个面向内容运营的 AI 工作台。我用 FastAPI 做后端，Vue3 做前端，LiteLLM 统一接入多个模型提供方，Agent 设计上分成两类，一类是固定四阶段的 Workflow Agent，用来完成策略、写作、编辑、审核；另一类是支持 tool calling 的 Chat Agent，用来完成内容生成、改写、排期、统计这些开放式任务。我还做了 SQLAlchemy 持久化、BackgroundTasks 和 Redis + RQ 两套任务模式，以及 24 个 pytest 测试用例，保证接口和流程稳定。`

`所以如果总结我的特点，我会说我不是只懂模型，也不是只会调接口，我更希望做的是把大模型能力和后端工程、前端交互、状态持久化、测试验证结合起来，做成真正可用的 Agent 应用。`

---

## 4. 高概率面试问题总图

你会被问的问题基本可以分成六类：

1. 你是谁，你为什么转 Agent 方向。
2. 你的 Agent 项目到底做了什么。
3. 你会不会 Python、FastAPI、SQLAlchemy、Redis、Vue3。
4. 你对 LLM、Agent、RAG 到底理解到什么程度。
5. 你简历里的实习和科研是不是你真的做过。
6. 你遇到问题时怎么分析、定位和权衡。

建议答题结构统一成：

`场景 -> 选择 -> 实现 -> 效果 -> 反思`

---

## 5. AI Content Ops Agent Platform 项目深度准备

这是你最重要的项目，必须准备到能扛住持续追问。

### 5.1 项目一句话定位

`这是一个面向内容运营场景的 Agent 应用原型，我把内容生成、改写、审核、排期和统计做成了一个完整闭环，而不是只做了一个调用大模型的聊天页面。`

### 5.2 项目价值怎么讲

你要强调这几个点：

- 不是单次生成，而是工作流闭环。
- 不是单模型调用，而是多 provider 路由。
- 不是一次性回复，而是有状态持久化。
- 不是 demo 代码，而是有测试和任务执行链路。

### 5.3 项目架构怎么讲

推荐口语化回答：

`前端我用 Vue3 + Pinia + Vue Router 做工作台，负责表单配置、任务发起、轮询 job、展示 Agent 步骤结果和内容预览。后端我用 FastAPI 做 API 层，按 routes、services、storage 分层，业务层里主要有内容生成服务、四阶段 Agent pipeline 和 Chat Agent。模型接入层用 LiteLLM 统一调用不同 provider，工具调用这块用 LangChain 的 tool calling 能力，但核心编排逻辑还是自己控制。存储层用 SQLAlchemy，把内容、日历、Agent thread、message、tool events、jobs 都做了持久化。异步任务层既支持 FastAPI BackgroundTasks，也支持 Redis + RQ。`

### 5.4 项目里的真实技术点

你必须能准确说出的真实指标：

- `4` 阶段 Workflow Agent
- `9` 个 Chat Agent 工具
- `4` 类模型提供方
- `24` 个 pytest 测试

不要说没有实现的内容：

- 不要说已经生产上线
- 不要说有登录、权限、多租户、计费
- 不要说接了真实社交平台自动发布

### 5.5 Workflow Agent 怎么讲

推荐回答：

`我把固定内容生产任务拆成了四个阶段：Strategy、Writer、Editor、Review。这样做的原因是内容生成不只是让模型直接吐最终结果，而是先明确策略，再写草稿，再编辑润色，最后审校打分。这样做的好处是流程更可控，前端还能展示每一步的状态、耗时和输出，便于调试和解释。`

继续追问时可以补：

- 每个阶段有独立的 `system_prompt`
- 每一步都会拿到前一步输出继续加工
- `review` 阶段温度会更低，强调稳定性
- 最终保存的是 `editor` 的结果，`review` 结果进入元数据

### 5.6 Chat Agent 怎么讲

推荐回答：

`Workflow Agent 适合固定流程，Chat Agent 适合开放式任务。比如用户可能会说“帮我看看最近内容”“把第 12 条内容改成更营销风格”“帮我安排下周发布计划”，这类需求更适合由 Chat Agent 决定是否调用工具。`

继续追问时可以补：

- 先拼接 system message、历史消息和当前用户消息
- 如果模型返回 tool calls，就找到本地对应工具函数执行
- 把工具结果作为 `ToolMessage` 回传给模型
- 最终再由模型生成自然语言回复
- 工具执行过程被记录为 `tool_events`

### 5.7 为什么分成两类 Agent

这是高频题。

推荐回答：

`因为两类任务的目标不同。Workflow Agent 强调流程稳定、结果可控、步骤可观测，更适合固定内容生产；Chat Agent 强调交互灵活和任务开放性，更适合查询、改写、排期这类操作。一个偏 workflow，一个偏 action。`

### 5.8 为什么用 LiteLLM

推荐回答：

`LiteLLM 的核心价值是统一不同 provider 的调用接口。我这个项目接了 Claude、SiliconFlow、DeepSeek、Moonshot，如果直接对接每家 SDK，业务层会很散。用 LiteLLM 之后，我只需要在服务层关心 provider、model、temperature、max_tokens 这些通用参数，切换 provider 的成本更低。`

### 5.9 为什么用 LangChain

推荐回答：

`我没有把整个工作流都交给 LangChain，我主要用了它的 message 抽象和 tool calling 能力。这样我可以复用它在工具调用上的成熟能力，但核心业务编排、状态管理和持久化还是自己控制，可控性更强。`

### 5.10 为什么用 FastAPI

推荐回答：

`因为这个项目是典型的 API 驱动应用，接口多、schema 多、需要依赖注入和请求校验。FastAPI 用 Pydantic 做请求响应建模，接口定义很清晰，自动文档也比较方便。相比 Flask，它更适合我这种接口为主、异步 IO 比较多的项目。`

### 5.11 为什么用 Vue3

推荐回答：

`前端交互比较多，但业务复杂度没有到需要 React 全家桶的程度。Vue3 的 Composition API、Pinia 和 Router 已经足够把页面状态、步骤状态和任务轮询组织清楚，开发效率比较高。`

### 5.12 为什么做两种任务模式

推荐回答：

`一套是 FastAPI BackgroundTasks，适合本地 demo 和轻量任务；另一套是 Redis + RQ，适合长耗时任务和更高并发场景。这样本地启动成本低，但又保留了向真正异步队列扩展的路径。`

### 5.13 为什么前端轮询 job

推荐回答：

`轮询实现简单、稳定，也更容易和后台任务队列对齐。这个项目的目标是先把闭环做完整，所以我优先选择实现成本更低的轮询模式，而不是一开始上 WebSocket 或 SSE。`

### 5.14 你在这个项目里最关键的贡献

推荐回答：

`我觉得最关键的不是把某个接口写出来，而是把大模型调用做成了完整系统。具体来说，一是把内容生成拆成了可观测的四阶段流程，二是把开放式任务做成了支持工具调用的 Chat Agent，三是把 thread、message、tool events、jobs 做了持久化，四是补了测试和异步任务链路。`

### 5.15 项目难点怎么讲

推荐回答：

`最大的难点不是单点技术，而是怎么把多个层面接起来。比如 Agent 不能只是调模型，还要考虑步骤状态、工具调用、任务超时、前端展示、失败处理和结果持久化。另一个难点是要控制项目边界，哪些是真实实现的，哪些是未来扩展的，不然项目很容易变成概念堆砌。`

### 5.16 如果面试官问“你为什么没用 LangGraph”

推荐回答：

`我知道 LangGraph 更适合做状态图式的 Agent 编排，但这个项目的流程相对简单，四阶段 pipeline 和工具调用逻辑我自己写就能覆盖，而且这样状态和持久化都更可控。对校招项目来说，我更看重对底层流程的理解，而不是把全部逻辑交给框架。`

### 5.17 如果面试官问“这个项目最大的不足是什么”

推荐回答：

`第一个不足是生产化能力还不够，比如登录、权限、多租户、监控这些没有做；第二个不足是任务结果获取目前主要靠轮询，实时性一般；第三个不足是 Agent 评测还比较轻，更多是契约测试和流程测试，系统性评测还可以继续补。`

### 5.18 如果面试官问“如果再做一版你会怎么优化”

推荐回答：

`我会优先做三件事。第一是把任务通知从轮询升级成 SSE 或 WebSocket；第二是把评测体系做完整，比如固定测试集、回归 case 和工具调用成功率统计；第三是补权限、多租户、日志监控这些更接近生产环境的能力。`

### 5.19 项目真实代码落点

你自己要熟悉这些文件：

- `src/api/main.py`
- `src/api/routes/content.py`
- `src/api/routes/agent.py`
- `src/api/routes/jobs.py`
- `src/api/services/content_service.py`
- `src/api/services/agent_pipeline.py`
- `src/api/services/chat_agent.py`
- `src/jobs/queue.py`
- `src/storage/content_store.py`
- `frontend/src/views/Studio.vue`
- `frontend/src/api/jobs.ts`

### 5.20 这个项目的高频追问清单

建议逐个练习：

1. 这个项目解决的核心问题是什么？
2. 为什么不是直接做一个聊天页面？
3. Workflow Agent 和 Chat Agent 区别是什么？
4. 为什么把状态持久化到数据库？
5. 为什么用 LiteLLM？
6. 为什么用 LangChain 但没有把编排全部交给它？
7. 为什么做 BackgroundTasks 和 RQ 两套模式？
8. 为什么前端轮询而不是 WebSocket？
9. 任务失败怎么处理？
10. 工具失败怎么处理？
11. 你怎么控制模型输出格式？
12. 你怎么做测试？
13. 这个项目能否扩展成生产系统？
14. 你做这个项目时最大的取舍是什么？
15. 这个项目最能体现你什么能力？

---

## 6. 天津行健科技实习准备

这段实习是你工程落地能力的重要证明，面试官很可能会问。

### 6.1 这段经历怎么定位

`这是我从算法和研究逐步转向 AI 应用工程的关键经历，我在这里接触了 Django 应用开发、RAG 知识库构建、测试和 Docker 部署。`

### 6.2 项目怎么讲

推荐回答：

`我参与的是金融领域 AI 应用开发，主要做了三块。一块是基于 Django 的前后端系统开发；一块是 RAG 知识库构建，包括文档清洗、分块和检索增强；还有一块是测试和质量保障，验证检索效果、接口逻辑和部署稳定性。`

### 6.3 Django 为什么用

推荐回答：

`当时项目偏快速交付，Django 自带 ORM、admin、路由和完整 Web 开发能力，适合快速搭一个稳定系统。如果是纯 API 驱动、异步接口多的场景，我会更偏向 FastAPI。`

### 6.4 RAG 这一段怎么讲

推荐回答：

`我主要参与的是文档切分策略和检索增强流程。因为金融文档段落之间关联比较强，如果简单按固定长度切，容易破坏语义连续性，所以我更关注语义连贯性优先的切分方式。我的目标是提高召回内容和用户问题之间的相关性，减少后续生成阶段的错误引用。`

### 6.5 如果被问“语义分块怎么做”

安全回答：

`我当时的思路不是只按固定 token 数切，而是结合文本语义相似度去判断切分边界，尽量让一个 chunk 保持语义完整。它不是纯理论研究，更偏工程上的规则和启发式设计，核心目标是提高检索质量。`

### 6.6 如果被问“RAG 为什么还会幻觉”

推荐回答：

`因为 RAG 只能改善上下文质量，不能彻底消除生成模型自身的不确定性。如果召回内容本身不准、问题和上下文对齐不好，或者 prompt 约束不够，最终答案还是可能出现幻觉。`

### 6.7 这段实习的高频问题

1. Django 和 FastAPI 有什么区别？
2. RAG 的完整链路是什么？
3. 固定 chunk 和语义 chunk 的区别？
4. top-k 怎么选？
5. 检索增强为什么仍然可能答错？
6. 你做了哪些测试？
7. Docker 部署做了什么？
8. Ngrok 为什么要用？

---

## 7. 北京交叉科技量化实习准备

这段经历和 Agent 岗不是完全同方向，但不是没用，你要学会转义。

### 7.1 怎么解释它和目标岗位的关系

推荐回答：

`虽然这段经历偏量化和高频策略，但它锻炼了我对工程稳定性、性能、数据回测和问题定位的意识。我现在求职方向更偏 Agent 应用，但这段经历让我在严谨性、指标意识和代码质量方面受益很大。`

### 7.2 如果被问“为什么从量化转 Agent”

推荐回答：

`我在量化实习里学到了很多工程和策略优化方法，但我长期更感兴趣的还是 AI 应用方向，尤其是把大模型能力做成真实可用系统。所以我希望把之前的工程严谨性和 AI 背景结合起来，转向 Agent 应用工程。`

---

## 8. 焊缝检测和多模态科研项目准备

这些项目不是你投递岗位的核心卖点，但能体现你有算法基础、能做实验、能吃硬问题。

### 8.1 你要突出什么

- 数据处理能力
- 模型训练与调优能力
- 多模态融合理解
- 指标意识
- 从研究走向工程的转化能力

### 8.2 焊缝点云项目怎么讲

推荐回答：

`这个项目主要是针对焊缝成形质量做在线检测。我做了点云分类和点云缺陷检测算法的适配与训练，并参与了可视化界面整合。它锻炼了我从数据、模型到应用展示这一整条链路的能力。`

### 8.3 多模态项目怎么讲

推荐回答：

`多模态项目主要是融合电弧视频和电信号做焊接质量识别。我参与了数据集构建、特征融合和模型轻量化方向的工作。这个过程让我对多模态数据对齐、鲁棒性和边缘部署约束有更直观的理解。`

### 8.4 如果被问“科研和 Agent 应用有什么关系”

推荐回答：

`科研训练了我拆问题、做实验、分析误差和迭代方案的能力，这些能力在 Agent 应用里仍然很重要。比如 Agent 系统同样需要做流程设计、失败分析、评测和优化，只是对象从感知模型变成了 LLM 应用系统。`

---

## 9. Python 高频八股

这部分是后端和 AI 应用岗位的基础盘。

### 9.1 生成器和迭代器

**问题**：什么是生成器？  
**回答**：生成器是按需产出数据的可迭代对象，不会一次性把所有结果放进内存，适合处理大数据流和惰性计算。Python 里用 `yield` 定义生成器函数。

**问题**：生成器和列表区别？  
**回答**：列表是一次性把所有结果都算出来并存储，访问快但占内存；生成器按需生成，省内存但只能逐步消费。

### 9.2 装饰器

**问题**：装饰器是什么？  
**回答**：本质上是接收函数并返回新函数的高阶函数，用于在不修改原函数代码的前提下增强行为，比如日志、鉴权、缓存。

### 9.3 深拷贝和浅拷贝

**问题**：深拷贝和浅拷贝区别？  
**回答**：浅拷贝只复制最外层对象，内部嵌套对象还是共享引用；深拷贝会递归复制所有层级，得到完全独立的对象。

### 9.4 GIL

**问题**：GIL 是什么？  
**回答**：GIL 是 CPython 里的全局解释器锁，同一时刻只允许一个线程执行 Python 字节码，所以多线程在 CPU 密集任务上不能真正并行，但在 IO 密集任务上依然有效，因为线程等待 IO 时会释放执行机会。

### 9.5 线程、进程、协程

**问题**：三者区别？  
**回答**：进程是资源隔离单位，适合 CPU 密集型；线程共享进程内存，切换成本比进程低，适合 IO 场景；协程是用户态调度，更轻量，适合高并发 IO。

### 9.6 `*args` 和 `**kwargs`

**问题**：作用是什么？  
**回答**：`*args` 接收任意数量的位置参数，`**kwargs` 接收任意数量的关键字参数，常用于写通用函数或包装函数。

### 9.7 列表推导式和生成器表达式

**问题**：区别？  
**回答**：列表推导式立即生成列表；生成器表达式按需生成，更省内存。

### 9.8 垃圾回收

**问题**：Python 垃圾回收机制？  
**回答**：主要是引用计数，辅以分代回收来处理循环引用。

---

## 10. FastAPI 高频八股

### 10.1 FastAPI 和 Flask 区别

**问题**：为什么你的项目用 FastAPI，不用 Flask？  
**回答**：FastAPI 更适合接口驱动项目，类型标注、Pydantic 校验、依赖注入和自动文档都比较完善；Flask 更轻量，但很多能力要自己补。我这个项目接口多、schema 多、异步 IO 比较多，所以 FastAPI 更顺手。

### 10.2 FastAPI 请求生命周期

**问题**：请求进入 FastAPI 之后发生了什么？  
**回答**：请求先到 Uvicorn，Uvicorn 作为 ASGI server 把 HTTP 请求转换成 ASGI 调用，再交给基于 Starlette 的 FastAPI 处理。FastAPI 会做路由匹配、中间件处理、依赖注入、Pydantic 校验，最后执行视图函数并把结果序列化成响应。

### 10.3 FastAPI 的 `async` 意义

**问题**：`async` 为什么快？  
**回答**：不是 CPU 更快，而是在等待 IO 时不会阻塞线程，比如等待 LLM API 响应、网络请求、数据库响应时，协程可以切换去处理别的任务，所以吞吐更高。

### 10.4 `Depends` 是什么

**问题**：FastAPI 依赖注入有什么价值？  
**回答**：它把对象创建和业务函数解耦，比如数据库 store、LLM client、chat service 不需要在每个接口里手动 new。这样复用方便、测试时也更容易 override。

### 10.5 Pydantic 做了什么

**问题**：Pydantic 在 FastAPI 里有什么作用？  
**回答**：主要负责请求数据校验、默认值处理、类型转换和响应序列化，也能自动生成 OpenAPI 文档。

### 10.6 中间件

**问题**：你项目里用到了什么中间件？  
**回答**：主要用了 CORS middleware，处理前后端跨域访问。请求先经过中间件，再进路由；响应返回时再反向经过中间件。

### 10.7 为什么 route 要薄

**问题**：为什么你把业务逻辑放到 service，不直接写在 route 里？  
**回答**：因为 route 的职责应该是参数接收、依赖注入和异常映射，业务逻辑放 service 更清晰，也更容易测试和复用。

### 10.8 你的异常处理策略

**问题**：后端错误怎么设计？  
**回答**：service 层抛业务异常，比如配置错误、内容不存在、模型调用失败；route 层把它们映射成 HTTP 400、404、502 等状态码，让前端和调用方能明确区分错误类型。

---

## 11. Django、Flask、FastAPI 对比准备

这块很容易被问，因为你简历里既有 Django 实习，又有 FastAPI 项目，面试官喜欢追问框架选择。

### 11.1 Django

适合：

- 快速搭完整 Web 应用
- 后台管理、ORM、模板都需要
- 团队偏传统 Web 开发

### 11.2 Flask

适合：

- 轻量服务
- 自定义程度高
- 项目规模不大

### 11.3 FastAPI

适合：

- API 驱动系统
- 需要 schema 校验和自动文档
- 需要 async IO
- 更现代的 Python 后端开发体验

### 11.4 面试时的比较答法

`Django 更像大而全框架，适合快速搭整站；Flask 更轻，适合自由组合；FastAPI 更偏现代 API 开发，特别适合我这种 Agent 应用、接口驱动、需要 Pydantic 和 async 的项目。`

---

## 12. SQLAlchemy、数据库、SQLite、PostgreSQL

### 12.1 为什么用 SQLAlchemy

**问题**：为什么不直接写 SQL？  
**回答**：SQLAlchemy 适合结构化状态建模，尤其是我这个项目要存内容、日历、thread、message、tool events、jobs，多表关系比较明显。ORM 能提升开发效率，也方便未来从 SQLite 切 PostgreSQL。

### 12.2 Engine 和 Session

**问题**：Engine 和 Session 区别？  
**回答**：Engine 管理数据库连接和连接池，Session 更像 ORM 的工作单元，负责对象状态跟踪、flush、commit、rollback。

### 12.3 `flush` 和 `commit`

**问题**：区别是什么？  
**回答**：`flush` 是把改动发送到数据库但还没真正提交事务；`commit` 是正式提交事务。通常 `commit` 前会自动 `flush`。

### 12.4 事务

**问题**：为什么要事务？  
**回答**：事务保证一组操作要么全部成功，要么全部失败回滚，避免状态不一致。

### 12.5 索引

**问题**：你什么时候会加索引？  
**回答**：常用于过滤、排序、关联条件上的字段，比如状态、创建时间、thread_id 这些高频查询字段。

### 12.6 SQLite 为什么够用

**问题**：为什么本地项目用 SQLite？  
**回答**：因为本地 demo 和轻量开发场景下 SQLite 足够简单。这个项目还加了 WAL 和 busy timeout，减少读写冲突。如果并发更高，我已经预留了 PostgreSQL + Redis + RQ 模式。

### 12.7 PostgreSQL 相比 SQLite 的优势

**回答**：更适合高并发、复杂事务、连接池管理和生产环境部署。

---

## 13. Redis、RQ、任务队列

### 13.1 为什么不用单纯接口同步执行

**问题**：为什么要任务队列？  
**回答**：因为 LLM 任务可能长耗时，如果一直挂在 API 请求里，会影响响应时间和吞吐。任务队列把执行和请求解耦，API 负责入队和查状态，worker 负责真正执行。

### 13.2 RQ 的执行流程

**回答**：客户端先创建 job，后端把任务元数据写数据库，再把任务放入 Redis 队列；worker 消费任务并执行；执行完成后把结果和状态回写数据库；前端通过 job 接口轮询拿结果。

### 13.3 为什么是 RQ，不是 Celery

**安全回答**：RQ 更轻量，接入门槛低，适合我这个项目的规模；Celery 更强大，但配置和概念更重。

### 13.4 限流怎么讲

**回答**：我做了 provider 级别的 inflight job 限流，避免同一模型提供方堆积过多长任务，把上游 API 打爆。

---

## 14. Vue3、Pinia、Vue Router、Vite

### 14.1 为什么用 Vue3

**回答**：Vue3 的 Composition API 比较适合复杂页面状态组织，Pinia 和 Router 配合起来也比较轻，适合快速做一个结构清晰的 AI 工作台。

### 14.2 Vue3 响应式原理

**问题**：Vue3 响应式底层是什么？  
**回答**：核心是 `Proxy + effect`。读取响应式数据时收集依赖，修改数据时触发依赖更新，所以模板和计算属性会自动重新计算。

### 14.3 `ref` 和 `reactive`

**回答**：`ref` 适合包装单值，`reactive` 适合对象和数组。模板里会自动解包 `ref`，JS 里需要 `.value`。

### 14.4 `computed` 和 `watch`

**回答**：`computed` 适合派生状态，有缓存；`watch` 适合副作用，比如监听变化后发请求、记日志、触发异步逻辑。

### 14.5 Pinia 做什么

**回答**：Pinia 用于管理跨组件、跨页面共享状态，比如内容列表、模型配置等。页面局部状态还是用组件内 `ref/reactive` 更合适。

### 14.6 路由懒加载

**回答**：通过 `() => import(...)` 按需加载页面，减少首屏包体积。

### 14.7 `nextTick`

**回答**：Vue 会把 DOM 更新放进调度队列，数据变了不一定立刻反映到 DOM。要读取更新后的 DOM，通常要等到 `nextTick`。

---

## 15. HTTP、REST、CORS 基础

### 15.1 GET 和 POST

**回答**：GET 主要用于获取资源，应该幂等；POST 更常用于创建或触发动作，通常不幂等。

### 15.2 常见状态码

- `200`：成功
- `201`：创建成功
- `400`：请求参数错误
- `401`：未认证
- `403`：无权限
- `404`：资源不存在
- `429`：请求过多
- `500`：服务端内部错误
- `502`：上游服务错误

### 15.3 什么是 CORS

**回答**：浏览器的跨域资源共享机制，当前端和后端域名、端口或协议不同，浏览器会限制跨域访问，需要后端显式允许。

---

## 16. pytest、测试、Mock、契约测试

### 16.1 为什么测 Agent 应用

**回答**：Agent 应用最不稳定的部分就是外部模型调用，所以我重点做的是不依赖真实 provider 的契约测试和流程测试，保证接口、步骤结构、状态持久化和异常映射是稳定的。

### 16.2 什么是契约测试

**回答**：契约测试关注接口输入输出格式和行为约定是否符合预期，不一定关心内部实现细节。

### 16.3 为什么用 fake LLM

**回答**：真实 LLM 调用成本高、结果不稳定、依赖外部网络，不适合作为默认测试。用 fake LLM 可以稳定复现输出，专注验证业务逻辑。

### 16.4 单元测试和集成测试区别

**回答**：单元测试关注单一函数或模块；集成测试关注多个模块拼起来之后是否正常协作。

---

## 17. Docker、部署、Ngrok

### 17.1 Docker 的价值

**回答**：Docker 把运行环境和依赖封装起来，减少“我这里能跑你那里不能跑”的问题，也更适合部署和迁移。

### 17.2 你在实习里 Docker 做了什么

**回答**：主要是把 Django 应用和相关依赖容器化，统一运行环境，方便部署到服务器并结合端口映射对外提供访问。

### 17.3 Ngrok 为什么要用

**回答**：Ngrok 主要是把本地或内网服务临时暴露到公网，便于远程访问和演示。

---

## 18. LLM 基础八股

### 18.1 temperature 是什么

**回答**：temperature 用来控制输出随机性，越高越发散，越低越稳定。内容创意类任务可以稍高，审校和结构化输出更适合较低温度。

### 18.2 top_p 是什么

**回答**：top_p 是核采样参数，控制采样时从累计概率前多少的 token 中选择，和 temperature 一样都在调输出多样性。

### 18.3 Prompt engineering 是什么

**回答**：本质上是通过设计上下文、角色、任务目标、约束条件和输出格式，提升模型完成任务的稳定性和质量。

### 18.4 幻觉是什么

**回答**：模型输出看起来合理但事实不正确或依据不足的内容。

### 18.5 上下文窗口是什么

**回答**：模型一次能处理的上下文长度上限，超过会被截断或丢失信息。

---

## 19. Agent、Tool Calling、LangChain、LiteLLM 八股

### 19.1 什么是 Agent

**回答**：如果简单说，Agent 就是能够基于目标进行多步决策、必要时调用工具、并根据中间结果继续推进任务的 LLM 应用形式。

### 19.2 Agent 和普通聊天模型区别

**回答**：普通聊天模型更多是一问一答；Agent 会进行任务拆解、工具调用、状态推进，有更强的行动能力。

### 19.3 为什么 Agent 需要工具

**回答**：因为很多任务不是靠纯语言生成能完成的，比如查数据库、改写已有内容、查日历、写状态，这些都需要真实执行能力。

### 19.4 Tool calling 的流程

**回答**：模型先返回要调用的工具名和参数，后端执行对应工具函数，再把结果回传给模型，模型再根据结果输出最终回复。

### 19.5 Agent 为什么需要状态持久化

**回答**：为了支持多轮会话、结果回放、失败排查、工具追踪和任务恢复。否则 Agent 每次都是无状态黑盒。

### 19.6 LangChain 你到底用了什么

**回答**：我主要用了它的 message 抽象和 StructuredTool 工具封装，没有把所有业务逻辑完全交给 LangChain。

### 19.7 LiteLLM 解决了什么问题

**回答**：统一多 provider 接口，简化模型切换和配置管理。

---

## 20. RAG 高频八股

### 20.1 RAG 是什么

**回答**：RAG 是 Retrieval-Augmented Generation，先从知识库检索相关内容，再把检索结果和用户问题一起提供给模型生成答案。

### 20.2 RAG 和微调区别

**回答**：RAG 是在推理阶段补外部知识，更新快、成本低；微调是调整模型参数，更适合风格、格式或特定能力强化。

### 20.3 文档分块为什么重要

**回答**：chunk 太大，噪声多；chunk 太小，语义不完整。分块质量会直接影响召回质量。

### 20.4 向量检索为什么会召回错误

**回答**：因为向量相似性并不等于真正语义正确，也可能被噪声、歧义词、领域术语或 chunk 切分方式影响。

### 20.5 top-k 怎么选

**回答**：top-k 不是越大越好，太小可能漏召回，太大可能把噪声也带进来，通常要结合实际数据集调。

---

## 21. 面试官喜欢抓的“底层机制”

这类问题不要硬背源码，但要能说运行逻辑。

### 21.1 FastAPI 底层关键词

- `Uvicorn`
- `ASGI`
- `Starlette`
- `Depends`
- `Pydantic`
- `middleware`
- `async IO`

### 21.2 Vue3 底层关键词

- `Proxy`
- `track`
- `trigger`
- `effect`
- `computed cache`
- `scheduler`
- `nextTick`

### 21.3 SQLAlchemy 底层关键词

- `engine`
- `connection pool`
- `session`
- `flush`
- `commit`
- `rollback`
- `unit of work`

### 21.4 Agent 底层关键词

- `message abstraction`
- `tool schema`
- `tool execution loop`
- `context window`
- `state persistence`
- `retry / timeout`

---

## 22. 简历高风险点清单

这些内容一旦写了就必须能展开：

### 22.1 “熟悉 Claude Code、Cursor、Codex、skills”

你需要准备至少一个真实例子：

`我会用 AI 编程工具做代码阅读、接口样板生成、测试用例草拟、重构建议和文档整理。skills 方面，我理解它本质上是把特定场景下的提示词、操作步骤和约束规则固化成可复用工作流，从而提升开发效率和一致性。`

### 22.2 “RAGFlow 流程、文档分块、向量化”

你至少要能说：

- 文档怎么清洗
- chunk 怎么切
- 检索怎么做
- 结果怎么评估

### 22.3 “量化全栈工程师”

你必须能回答：

- 做了哪些策略开发工作
- 你具体写了什么代码
- 为什么现在转 Agent

### 22.4 论文和作者顺位

你必须准确说出：

- 论文题目
- 你负责的部分
- 实验或算法的关键点
- 你不是第一作者时，你的真实贡献是什么

---

## 23. 简历真实性原则

这几条一定记住：

1. 不要把“了解”说成“精通”。
2. 不要把“参与”说成“主导”。
3. 不要把“demo 原型”说成“生产系统”。
4. 不要把“调接口”说成“做了底层框架”。
5. 不会的底层问题可以说理解到机制层，但不要瞎编源码细节。

推荐说法：

- `这个点我在项目里主要用到了……`
- `从机制上我目前理解是……`
- `如果继续深到源码实现，我没有系统读过源码，但运行逻辑我能说明。`

---

## 24. 高频行为面试题

### 24.1 你为什么想做 Agent 应用工程师

推荐回答：

`我发现自己比起纯算法研究，更喜欢把模型能力做成真正可用的系统。Agent 应用工程师这个方向正好把后端开发、LLM 能力、业务流程和产品闭环结合起来，和我的经历也比较契合。`

### 24.2 你最大的优点是什么

推荐回答：

`我比较擅长把复杂问题拆开来做。无论是科研项目、RAG 系统还是 Agent 应用，我都会先拆清楚数据流、状态流和职责边界，再逐步实现和验证。`

### 24.3 你最大的缺点是什么

推荐回答：

`我有时候会在细节打磨上投入比较多时间。现在我会更有意识地区分 demo、原型和生产级目标，先把核心闭环做完整，再逐步优化细节。`

### 24.4 你遇到过最难的问题是什么

建议从项目里选一个：

- Agent 项目里状态、工具调用和前端展示如何打通
- RAG 项目里文档分块和检索质量的取舍
- 多模态项目里数据对齐和模型鲁棒性问题

### 24.5 团队协作问题

如果面试官问你如何合作，可以答：

`我习惯先统一接口和数据结构，再分别推进开发和验证。做项目时我会比较重视边界清晰、文档补充和问题复现路径。`

---

## 25. 面试问答清单

下面这份清单建议你逐题口头回答一遍。

### 25.1 自我介绍类

1. 请做一个自我介绍。
2. 你为什么从多模态算法转向 Agent 应用？
3. 你为什么选择这个岗位？
4. 你最想让我们记住你的哪一点？

### 25.2 Agent 项目类

5. 这个项目解决了什么问题？
6. 为什么它不是一个普通聊天系统？
7. 项目的整体架构是什么？
8. 为什么要做 4 阶段 Workflow Agent？
9. 为什么还要做 Chat Agent？
10. tool calling 是怎么工作的？
11. 你为什么用 LiteLLM？
12. 你为什么用 LangChain？
13. 你为什么用 FastAPI？
14. 你为什么用 Vue3？
15. 为什么要持久化 thread 和 tool events？
16. 为什么要两种任务模式？
17. 为什么选择轮询 job？
18. 你怎么处理任务失败？
19. 你怎么处理工具调用失败？
20. 你怎么做测试？
21. 项目里最难的地方是什么？
22. 如果再做一版你会优化什么？

### 25.3 Django / RAG 实习类

23. 你在 Django 项目里具体负责什么？
24. Django 和 FastAPI 区别是什么？
25. RAG 的完整链路是什么？
26. 文档为什么要分块？
27. 你怎么判断分块效果好不好？
28. 检索为什么会不准？
29. 你做了哪些测试？
30. Docker 和 Ngrok 在这个项目里起什么作用？

### 25.4 Python / 后端类

31. Python 的 GIL 是什么？
32. 线程、进程、协程的区别？
33. 生成器有什么用？
34. 装饰器是什么？
35. FastAPI 的请求生命周期？
36. Pydantic 有什么价值？
37. SQLAlchemy 的 Session 是什么？
38. `flush` 和 `commit` 区别？
39. Redis 为什么适合做任务队列中间件？
40. HTTP 常见状态码和含义？

### 25.5 前端类

41. Vue3 响应式原理是什么？
42. `ref` 和 `reactive` 区别？
43. `computed` 和 `watch` 区别？
44. Pinia 解决什么问题？
45. 前端轮询任务结果怎么实现？

### 25.6 LLM / Agent / RAG 类

46. temperature 的作用是什么？
47. 什么是幻觉？
48. Agent 和普通对话有什么区别？
49. 为什么 Agent 需要工具？
50. RAG 和微调区别是什么？
51. 多 provider 路由有什么价值？
52. 什么是上下文窗口？

### 25.7 科研和经历迁移类

53. 多模态项目里你最大的技术收获是什么？
54. 论文里你做了哪些具体工作？
55. 量化实习和 Agent 岗的关系是什么？
56. 你为什么不继续做纯算法或量化？

---

## 26. 7 天准备计划

### 第 1 天

- 写熟 30 秒、1 分钟、3 分钟自我介绍
- 把转方向逻辑讲顺

### 第 2 天

- 重点复习 `AI Content Ops Agent Platform`
- 手绘一张项目架构图
- 口头讲 3 遍项目流程

### 第 3 天

- 复习 `FastAPI + SQLAlchemy + Redis + pytest`
- 把底层关键词和常见问答过一遍

### 第 4 天

- 复习 `Vue3 + Pinia + Router + Vite`
- 复习前端和后端怎么交互

### 第 5 天

- 复习 `LLM + Agent + LiteLLM + LangChain + RAG`
- 把 tool calling 和 RAG 链路讲顺

### 第 6 天

- 复习 `Django/RAG 实习` 和 `多模态项目`
- 重点练“为什么转 Agent”

### 第 7 天

- 做一次完整模拟面试
- 把所有卡壳问题单独记下来
- 只补不会的，不要无限扩展

---

## 27. 面试前一晚检查清单

- 自我介绍能否不看稿讲顺
- Agent 项目能否讲 3 分钟
- Workflow Agent 和 Chat Agent 区别是否熟
- LiteLLM、LangChain、RAG 是否能解释
- FastAPI 和 Django 是否能比较
- Vue3 基础问题是否能答
- SQLAlchemy、Redis、RQ 是否有基本理解
- 论文和实习细节是否准确
- 时间线是否自洽
- 简历里每一个数字是否都能解释

---

## 28. 面试时的答题原则

1. 先答项目里的真实场景，再补概念。
2. 不会的底层不要硬编源码。
3. 少说“我精通”，多说“我在项目里这样用过”。
4. 如果问题很泛，先主动限定范围。
5. 如果被追问，优先回答机制和取舍。

推荐万能句式：

- `在我这个项目里，这个问题主要体现在……`
- `我当时选择这个方案，主要考虑的是……`
- `从机制上看，它本质上是……`
- `这个方案的好处是……，代价是……`
- `如果做生产化，我会进一步……`

---

## 29. 最后一句提醒

你最大的优势不是单点技术，而是能把：

- 算法理解
- Python 后端
- AI 应用
- Agent 工作流
- 测试和状态管理

串成一个完整故事。

真正面试时，不要试图表现成“我把每个框架源码都看完了”，而是要表现成：

`我能把问题拆开，我能把系统做出来，我知道为什么这么选，我知道下一步怎么优化。`

---

## 30. 项目技术实现链路详解

这一节不是八股，而是把仓库里的真实实现路径拆开。技术面时，如果面试官问“你这个功能到底怎么跑起来的”，你就按这一节回答。

### 30.1 后端总分层

这个项目后端可以概括成四层：

- `routes`：处理 HTTP 请求、参数校验后的对象接收、状态码映射。
- `services`：业务逻辑，比如内容生成、Agent pipeline、Chat Agent。
- `llm`：模型适配层，用 `LiteLLMClient` 统一调用不同 provider。
- `storage`：SQLAlchemy 持久化层，负责内容、thread、message、job 等状态存储。

对应代码入口：

- `src/api/main.py`
- `src/api/routes/*.py`
- `src/api/services/*.py`
- `src/llm/litellm_client.py`
- `src/storage/content_store.py`

### 30.2 内容生成接口链路

以 `POST /api/content/generate` 为例，调用链是：

1. 前端调用 `frontend/src/api/content.ts` 的 `generateContent`。
2. Axios 请求进入 `/api/content/generate`。
3. `src/api/routes/content.py` 中的 `generate_content` 接收 `GenerateRequest`。
4. `GenerateRequest` 由 Pydantic 校验字段，比如 `topic`、`content_type`、`temperature`、`max_tokens`。
5. 路由层通过 `Depends` 注入 `ContentStore` 和 `LiteLLMClient`。
6. 路由调用 `src/api/services/content_service.py` 的 `generate_content`。
7. service 内先 `resolve_provider`，再根据 `content_type` 构造不同 prompt。
8. `LiteLLMClient.generate_from_prompts` 把 system prompt 和 user prompt 组装成 messages。
9. `LiteLLMClient` 内部调用 `litellm.acompletion`，并通过 `asyncio.wait_for` 做超时控制。
10. 返回文本后，`parse_generated_content` 负责从模型输出中解析标题、正文、标签。
11. `ContentStore.save_content` 把内容存进数据库。
12. 路由层把结果整理成 `GenerateResponse` 返回给前端。

这一段你可以口语化概括成：

`先由 FastAPI 用 Pydantic 校验请求，再进入 service 构造 prompt，通过 LiteLLM 统一请求不同 provider，拿到模型输出后做结构解析，最后持久化到数据库并返回标准化响应。`

### 30.3 Agent Pipeline 链路

`POST /api/agent/run` 是四阶段 Workflow Agent 的入口。

调用链：

1. 路由层接收 `AgentRunRequest`。
2. 调用 `run_agent_pipeline`。
3. `run_agent_pipeline` 内部根据请求生成 `run_id`、`thread_id`、`steps` 容器。
4. 依次遍历 `AGENTS` 常量中的四个角色：`strategy`、`writer`、`editor`、`review`。
5. 每一阶段都会生成一个 `AgentStep`，初始状态是 `running`。
6. 每一阶段都通过 `llm.generate_from_prompts` 调模型。
7. `writer` 阶段会吃 `strategy` 输出，`editor` 会吃 `strategy + writer` 输出，`review` 会吃最终内容。
8. 每一步都会记录 `duration_ms`。
9. 如果中间某一步失败，会抛 `PipelineExecutionError`，同时把已经完成和失败的步骤一起返回。
10. 如果成功，最终内容来自 `editor` 输出，`review` 输出作为元数据存储。
11. 如果 `save_final=True`，会创建内容记录并把状态更新成 `agent_final`。

你可以强调的设计点：

- 工作流是顺序编排，不是让模型自己决定步骤。
- 每一步都显式记录状态、输入摘要、输出和耗时。
- 失败时不是只返回“失败”，而是返回失败在哪一步。

### 30.4 Chat Agent 链路

`POST /api/agent/chat` 的核心不是普通多轮聊天，而是“带工具调用的持久化 Agent”。

真实链路：

1. 路由层接收 `ChatRequest`。
2. `ChatAgentService.chat` 先解析 provider 和 model。
3. 如果没有传 `thread_id`，就自动生成一个。
4. 先 `upsert_agent_thread`，把 thread 元数据写入或更新。
5. 读取最近 `20` 条历史消息。
6. 先把当前用户消息持久化成一条 `agent_message`。
7. 进入 `_run_agent`。
8. `_run_agent` 先构建工具列表 `_build_tools`。
9. 再创建具体的聊天模型实例；Claude 走 `ChatAnthropic`，其他 provider 走 `ChatOpenAI + base_url`。
10. 如果模型支持 `bind_tools`，就把工具 schema 绑定给模型。
11. 消息列表由 `SystemMessage + 历史消息 + 当前 HumanMessage` 组成。
12. 最多循环 `4` 次：
13. 每轮先 `ainvoke(messages)`。
14. 如果模型没有返回 `tool_calls`，说明结束，直接返回自然语言回复。
15. 如果模型返回了 `tool_calls`，就逐个找到对应工具执行。
16. 工具结果会被转成 `ToolMessage` 追加回消息列表。
17. 同时记录 `ChatToolEvent`，包括 `name`、`args`、`output`、`status`、`error`。
18. 循环结束后，把 assistant 消息和 `tool_events` 一并持久化。

这里最容易被问的点：

- 为什么 history 只取最近 `20` 条？
  这是一个简单的上下文窗口控制策略，避免 thread 无限膨胀。
- 为什么工具调用循环只做 `4` 轮？
  防止模型陷入无休止 tool loop。
- 为什么要保存 `tool_events`？
  为了回放、调试、前端展示和排查工具执行问题。

### 30.5 Job 异步任务链路

以 `POST /api/jobs/agent-run` 为例：

1. 前端先创建 job，不直接等待最终 Agent 结果。
2. `src/api/routes/jobs.py` 调用 `create_and_enqueue_job`。
3. `create_and_enqueue_job` 先检查 provider 的 inflight job 数量是否超过阈值。
4. 如果没超，先在数据库里创建一条 `jobs` 记录，状态为 `queued`。
5. 再根据配置决定使用：
   `background` 模式：直接 `background_tasks.add_task(run_job, ...)`
   `rq` 模式：推送到 Redis 队列，由 worker 异步执行。
6. `run_job` 会读取 job 记录，更新状态为 `running`。
7. 再根据 `job_type` 构造不同 request 对象：
   `GenerateRequest`
   `AgentRunRequest`
   `RefineRequest`
   `TitleRequest`
   `SeoRequest`
8. 执行完成后，把结果 JSON 序列化写回 `jobs.result`。
9. 前端通过 `GET /api/jobs/{job_id}` 轮询状态。

### 30.6 模型列表接口链路

`GET /api/models` 做的不是简单返回写死列表，它有动态获取和回退策略。

具体逻辑：

1. 遍历所有支持的 provider。
2. 对每个 provider 尝试动态请求模型列表。
3. Claude 走 Anthropic 官方接口。
4. DeepSeek / Moonshot 走 OpenAI-compatible `/models` 接口。
5. SiliconFlow 走它自己的模型接口。
6. 请求结果会做 `5` 分钟 TTL 缓存。
7. 如果接口调用失败或 provider 未配置 key，就回退到代码里预设的 `fallback_models`。

这一段很适合回答“你是怎么做多模型控制台的”。

### 30.7 数据持久化链路

数据库里存的不是一张内容表，而是几类状态：

- `contents`：内容本体
- `calendar_events`：排期
- `content_metrics`：统计
- `agent_threads`：会话线程
- `agent_messages`：消息
- `jobs`：后台任务

其中几个关键字段设计：

- `contents.keywords`、`contents.tags` 用 JSON 文本存
- `agent_messages.tool_events` 用 JSON 文本存
- `jobs.payload` 和 `jobs.result` 也序列化成 JSON 文本

这样做的原因：

- 实现简单
- SQLite / PostgreSQL 都能兼容
- 对这个 demo 的查询模式已经足够

缺点也要知道：

- JSON 文本字段不适合做复杂条件查询
- 如果系统继续扩大，部分字段应该拆结构表或改 JSONB

### 30.8 前端 Studio 页面链路

`frontend/src/views/Studio.vue` 是最重要的前端页面。

它做的事情：

1. 维护一个表单对象：主题、平台、风格、关键词、长度、provider、model、temperature、max_tokens。
2. 点击“运行 Agent 流程”时，不直接调用 `/agent/run`，而是优先走 `/jobs/agent-run`。
3. 前端保存当前 job 状态。
4. 通过 `waitForJobResult` 每 `1.5s` 轮询一次 job。
5. 收到结果后，把 `steps`、`final_content`、`saved_content_id` 展示在右侧流程区和中间编辑区。
6. 页面中间可继续人工编辑，右侧展示步骤输出，左侧可以重新配置模型参数。

你可以总结成：

`Studio 不是单纯表单提交，而是一个面向任务执行和过程展示的工作台。`

### 30.9 Refine 页面链路

`frontend/src/views/Refine.vue` 展示了另一个重要模式：对已有内容做异步二次处理。

核心流程：

1. 先通过 `/content` 或 `/content/{id}` 选择一条已有内容。
2. 用户可以选四类操作：改写、风格切换、标题建议、SEO 分析。
3. 所有操作都走 job 接口，不同步阻塞页面。
4. 页面右侧用一个统一的 `resultText` 显示输出。
5. 轮询过程中显示 job 进度百分比和状态。

### 30.10 Chat 页面链路

`frontend/src/views/Chat.vue` 的关键点不是 UI，而是 thread 和 tool event 的前端消费。

真实逻辑：

1. 页面挂载时先拉取 thread 列表。
2. 点击 thread 时请求 `/agent/threads/{id}/messages`。
3. 发送消息时，前端先本地插入一条 `pending` 的 user message。
4. 请求成功后，再插入 assistant message。
5. 如果有 `tool_events`，就在 assistant message 下面展开显示工具名和结果。
6. 如果当前没有 thread，后端会自动创建一个并返回 thread_id。

### 30.11 错误处理链路

这个项目错误处理比较统一：

- Pydantic 参数错误：`422`
- 非法 provider 或业务参数错误：`400`
- 内容或 thread 不存在：`404`
- provider inflight job 超限：`429`
- 模型调用失败：`502`
- 队列不可用：`503`

前端侧用 Axios interceptor 统一把 `error.response.data.detail` 抽出来包装成 `ApiError`。

所以你回答“前后端怎么做错误处理”时，可以直接说：

`后端把错误分层映射成明确的 HTTP 语义，前端再统一解包成 ApiError，最后在页面上用 Element Plus message 或 error alert 呈现。`

---

## 31. 使用技术的实现细节和面试深挖点

这一节专门回答“不是只会用，而是你知道它在项目里怎么实现”。

### 31.1 FastAPI 实现细节

#### 31.1.1 为什么 route 尽量薄

在这个项目里，route 只负责四件事：

- 接收 request schema
- 通过 `Depends` 拿依赖
- 调 service
- 把异常映射成 HTTP 错误

好处：

- service 更容易单测
- 路由不会变成上百行大函数
- 业务逻辑可复用到 job runner

你可以举例：

- `/api/content/generate`
- `/api/agent/run`
- `/api/agent/chat`

它们都符合这个模式。

#### 31.1.2 `Depends` 在项目里的真实用法

主要依赖有：

- `get_store`
- `get_litellm_client`
- `get_chat_agent_service`

其中 `get_store` 用了 `lru_cache(maxsize=1)`，这意味着进程内复用同一个 `ContentStore` 实例，避免每个请求都重新初始化数据库 engine。

可以被追问：

- 为什么 store 可以缓存？
  因为 store 持有 engine 和 session factory，不是某个请求的临时事务对象。
- 为什么 LLM client 不缓存？
  因为它本身是轻量适配器，没有必要复杂化生命周期。

#### 31.1.3 为什么有的接口是 `async def`，有的是 `def`

这个项目里：

- 调模型、Agent、job 触发这类偏 IO 的接口多用 `async def`
- 简单查询接口可以是同步 `def`

底层原因：

- `async` 更适合 IO-bound
- 不是所有代码都 async 才“高级”
- 如果数据库层还是同步 ORM，实现上保持一致也更简单

#### 31.1.4 为什么 Pydantic 会返回 `422`

如果字段本身不合法，比如：

- `length="extra-long"`
- `max_tokens` 小于最小值
- `content_id <= 0`

这是 schema 校验错误，FastAPI 会直接返回 `422 Unprocessable Entity`。

如果字段结构合法，但业务上无效，比如：

- `provider="unknown"`

这是业务错误，代码里手动返回 `400`。

这个区别面试官很喜欢问。

#### 31.1.5 为什么要写 `response_model`

作用有三个：

- 约束返回结构
- 自动生成文档
- 防止内部字段不小心暴露

比如 thread 接口只返回 `AgentThreadResponse` 允许的字段，不会把 ORM 对象原样暴露。

#### 31.1.6 为什么有 `/stream` 接口但没真正做流式聊天

这是一个很好的主动说明点：

`我保留了 SSE transport 的入口，用于证明这个系统未来可以扩展成流式回复，但当前版本主流程还是以完整响应和任务轮询为主。这样边界更清晰，也减少了复杂度。`

### 31.2 LiteLLM 实现细节

#### 31.2.1 这个项目为什么要包一层 `LiteLLMClient`

如果直接在 service 里写 `litellm.acompletion`，问题是：

- 每个 service 都要自己拼 request
- 每个地方都要自己处理 key、base_url、timeout、异常
- provider 细节会泄漏到业务层

封装后业务层只关心：

- `provider`
- `model`
- `messages`
- `temperature`
- `max_tokens`

#### 31.2.2 provider 和 model 是怎么映射的

`config.get_litellm_model` 里有一层转换：

- SiliconFlow 模型会加 `openai/` 前缀
- DeepSeek 模型会加 `deepseek/` 前缀
- Moonshot 模型会加 `moonshot/` 前缀
- Claude 保持 Anthropic 侧模型名

这个细节很重要，因为说明你知道 LiteLLM 不是“魔法”，不同 provider 仍然需要适配。

#### 31.2.3 timeout 怎么做

不是只依赖 provider SDK 的默认超时，而是用：

- `asyncio.wait_for(...)`

外层再包一次统一超时逻辑，这样后端对超时语义有主动控制权。

#### 31.2.4 为什么把异常再包装一层

`LiteLLMClient` 会把：

- 导入失败
- provider key 缺失
- 超时
- provider 请求错误
- 空响应

统一映射成：

- `LLMConfigurationError`
- `LLMGenerationError`

好处是 route 层不用理解底层 provider 的所有异常类型。

### 31.3 LangChain / Tool Calling 实现细节

#### 31.3.1 为什么用 `StructuredTool`

因为工具调用最核心的是：

- 工具有名字
- 工具有参数 schema
- 模型能感知工具签名

`StructuredTool.from_function` 正好能把普通 Python 函数封装成模型可识别工具。

#### 31.3.2 工具是怎么分同步和异步的

这个项目里：

- 调 LLM 的工具，如 `create_content`、`refine_content`、`generate_title_options`、`optimize_seo` 是 `async`
- 简单查数据库的工具，如 `view_content`、`list_recent_contents`、`get_content_stats` 是同步函数

这是一个不错的回答点，说明你不是机械地所有函数都写成 async。

#### 31.3.3 为什么 `_run_agent` 最多循环 4 次

因为工具调用有可能出现：

- 模型反复调用同一工具
- 工具结果不满足模型预期又继续调用
- prompt 写不好导致死循环

限制轮数是一种防御式设计。

#### 31.3.4 为什么历史消息只保留 assistant 成功消息

`_history_to_messages` 里只把：

- user message
- `status == completed` 的 assistant message

写回模型上下文。

这样做是为了避免失败回复污染后续对话。

### 31.4 SQLAlchemy / SQLite 实现细节

#### 31.4.1 为什么 `ContentStore` 自己管理 session

这个项目没有直接把 ORM Session 暴露到各处，而是让 `ContentStore` 内部：

- `SessionLocal()`
- try/except
- commit/rollback
- finally close

这种方式对 demo 项目更简单，职责也更集中。

#### 31.4.2 为什么 SQLite 要设置 WAL 和 busy timeout

代码里做了：

- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=30000`

目的：

- WAL 提升并发读写体验
- busy timeout 减少“database is locked”报错

如果面试官抓这个点，这是很加分的细节。

#### 31.4.3 为什么 JSON 文本字段没有直接建子表

因为这个项目当前查询需求主要是：

- 按主键取内容
- 列表查看内容
- 展示 thread/message/tool events

工具事件等结构更多是“记录”和“回放”，不是复杂统计分析，所以先用 JSON 文本够用。

#### 31.4.4 job 状态机怎么设计

job 有几个主要状态：

- `queued`
- `running`
- `completed`
- `failed`

还有伴随字段：

- `progress`
- `attempts`
- `error`
- `started_at`
- `completed_at`

这是一个很典型的“可轮询任务状态机”设计。

### 31.5 Redis / RQ 实现细节

#### 31.5.1 为什么 job 元数据还要落数据库，不只放 Redis

因为前端要稳定查询 job 状态，Redis 队列更偏“传递任务”，数据库更适合做业务状态查询。

如果只依赖 RQ 内部状态，问题是：

- 前端查询方式更受限
- 状态模型不统一
- 换队列框架成本更高

#### 31.5.2 `run_job` 为什么是独立函数

因为 RQ 需要用 dotted path 导入 worker 执行函数，比如：

- `"src.jobs.runner.run_job"`

这也是为什么 `run_job` 要放在模块顶层。

### 31.6 Vue3 / Pinia / Axios 实现细节

#### 31.6.1 为什么 Axios 要做 interceptor

因为后端错误格式统一是：

- `{"detail": "..."}`
- 或 `{"detail": {"message": "...", ...}}`

前端用 interceptor 统一提取 message，组件层就不用每次自己解析 response 结构。

#### 31.6.2 `ModelSelector` 的状态同步怎么实现

`ModelSelector.vue` 里有两个关键 watch：

- watch `props.modelValue`，把父组件传入值同步到本地 reactive 对象
- watch 本地 `local`，变化后 emit 回父组件

这是典型的“受控组件”写法。

#### 31.6.3 为什么前端 job 轮询用 `while + setTimeout`

`waitForJobResult` 做了一个简单轮询器：

- 记录开始时间
- 循环请求 job 状态
- `completed` 就提取结果
- `failed` 就抛错
- 否则 sleep 1.5 秒继续

这是非常标准、也很容易讲清楚的实现。

#### 31.6.4 Chat 页面的 pending message 有什么价值

发送消息时先本地插一条 `pending` 的 user 消息，能让用户马上看到自己的输入被接收了，减少等待感。

### 31.7 测试实现细节

#### 31.7.1 为什么用 dependency overrides

FastAPI 的 `app.dependency_overrides` 可以在测试里把：

- `get_store`
- `get_litellm_client`
- `get_chat_agent_service`

替换成 fake 对象。

这样测试时不会访问真实数据库路径和真实 LLM provider。

#### 31.7.2 `FakeLLMClient` 测什么

它不是简单返回一个固定字符串，而是会根据不同 `system_prompt` 返回不同阶段输出，这样就能验证：

- strategy / writer / editor / review 的阶段顺序
- pipeline 最终保存结果
- 某一步失败时异常如何向上冒泡

#### 31.7.3 `FakeChatModel` 测什么

它能模拟两种情况：

- 正常 assistant reply
- 带 `tool_calls` 的 reply

所以可以验证：

- thread 消息是否持久化
- 历史消息是否被正确喂回模型
- tool events 是否被保存

---

## 32. 更完整的技术八股题库

这一节按“面试官可能连续追问”的方式整理。你不一定全背，但至少要知道哪些是重点。

### 32.1 Python 扩展八股

#### 问：可变对象和不可变对象有哪些

答：

- 不可变：`int`、`float`、`str`、`tuple`
- 可变：`list`、`dict`、`set`

可变对象在函数传参、浅拷贝和默认参数上都容易出问题。

#### 问：为什么函数默认参数不要写 `[]`

答：

因为默认参数在函数定义时只创建一次，如果是可变对象，多次调用会共享同一个对象。

#### 问：`is` 和 `==` 区别

答：

- `==` 比较值
- `is` 比较对象身份，也就是是不是同一个对象

#### 问：闭包是什么

答：

闭包就是内部函数引用了外部函数作用域中的变量，即使外部函数返回后，这些变量仍然能被内部函数访问。

#### 问：装饰器为什么常配合 `functools.wraps`

答：

为了保留原函数的 `__name__`、`__doc__` 等元数据，避免调试和文档信息丢失。

#### 问：什么是鸭子类型

答：

Python 更关注对象“能不能这样用”，而不是它是不是某个显式类型。

#### 问：协程和回调的区别

答：

协程本质上还是异步编程，但语义更线性、更接近同步代码，阅读和异常处理都更自然。

#### 问：Python 里的上下文管理器是做什么的

答：

用于管理资源的申请和释放，比如文件、连接、锁。`with` 结束后一定会执行清理逻辑。

### 32.2 HTTP / 网络扩展八股

#### 问：HTTP 和 HTTPS 区别

答：

HTTPS 在 HTTP 之上加了 TLS，保证传输加密、身份认证和完整性校验。

#### 问：什么是幂等性

答：

同一个请求执行一次和执行多次，结果一致，就叫幂等。典型如 GET、PUT、DELETE。

#### 问：什么是无状态协议

答：

HTTP 本身不记住前一次请求状态，每次请求理论上都是独立的，会话状态通常靠 Cookie、Session、JWT 等机制补充。

#### 问：Cookie、Session、JWT 区别

答：

- Cookie 是浏览器存储机制
- Session 是服务端保存会话状态
- JWT 是客户端可携带的自描述令牌

### 32.3 FastAPI / 后端扩展八股

#### 问：为什么 ASGI 比 WSGI 更适合现代 AI 应用

答：

因为 ASGI 原生支持异步和长连接，更适合高并发 IO、SSE、WebSocket 和长耗时外部 API 调用。

#### 问：FastAPI 基于什么

答：

底层基于 Starlette，数据校验和序列化依赖 Pydantic。

#### 问：为什么路由里要显式声明 `status_code=status.HTTP_201_CREATED`

答：

因为它表达语义更明确，也能让 OpenAPI 文档自动体现创建资源的返回状态。

#### 问：如果 service 里直接抛原始异常会怎样

答：

route 层就很难统一映射错误语义，也容易把底层错误细节直接暴露出去，所以要做异常抽象。

### 32.4 数据库扩展八股

#### 问：什么情况下索引反而会拖慢性能

答：

- 写入频繁时，索引维护有额外开销
- 低区分度字段索引价值小
- 查询没走索引时，额外索引也只是负担

#### 问：什么是联合索引最左前缀原则

答：

联合索引在匹配查询条件时，会优先从最左列开始利用索引。

#### 问：事务的四个特性 ACID

答：

- 原子性
- 一致性
- 隔离性
- 持久性

#### 问：隔离级别有哪些

答：

- Read Uncommitted
- Read Committed
- Repeatable Read
- Serializable

#### 问：什么是脏读、不可重复读、幻读

答：

- 脏读：读到未提交数据
- 不可重复读：同一行两次读结果不同
- 幻读：同一条件两次查询，行数变化

### 32.5 Redis 扩展八股

#### 问：Redis 为什么快

答：

- 基于内存
- 数据结构简单高效
- 单线程模型避免大量锁竞争
- 网络模型高效

#### 问：Redis 常用数据结构

答：

- string
- list
- hash
- set
- zset

#### 问：缓存穿透、击穿、雪崩

答：

- 穿透：查不存在的数据，缓存和数据库都被打
- 击穿：热点 key 失效瞬间大量请求打到后端
- 雪崩：大量 key 同时失效

#### 问：怎么缓解

答：

- 穿透：布隆过滤器、空值缓存
- 击穿：互斥锁、热点永不过期
- 雪崩：过期时间打散、多级缓存

### 32.6 Vue3 扩展八股

#### 问：为什么 Vue3 用 Proxy 替代 Object.defineProperty

答：

Proxy 能直接拦截整个对象的更多操作，比如新增属性、删除属性、数组操作，能力更完整。

#### 问：组件通信方式有哪些

答：

- props / emit
- provide / inject
- Pinia
- 事件总线

#### 问：为什么计算属性有缓存

答：

因为它本质是基于依赖的惰性求值，依赖不变时不会重复计算。

#### 问：为什么 watch 更适合异步请求

答：

因为 watch 是副作用工具，而 computed 更适合纯派生值。

### 32.7 Docker 扩展八股

#### 问：镜像和容器区别

答：

- 镜像是静态模板
- 容器是镜像运行后的实例

#### 问：为什么容器化对 AI 应用有价值

答：

因为依赖复杂、环境差异大，容器化可以提升部署一致性。

### 32.8 LLM / Agent 扩展八股

#### 问：function calling 和普通 prompt 输出 JSON 的区别

答：

function calling 更适合把模型输出约束成工具调用意图，减少自由文本歧义；普通 JSON 输出更依赖 prompt 约束。

#### 问：为什么 Agent 会“胡乱调工具”

答：

因为模型只是根据上下文概率选择行为，如果工具描述不清、提示词不严谨，模型可能误判应该调用哪个工具。

#### 问：怎么减少工具调用错误

答：

- 工具名明确
- 参数 schema 清晰
- 系统提示限制边界
- 失败信息可回传
- 工具数量不要无节制膨胀

#### 问：上下文污染是什么

答：

历史消息或工具结果中混入错误或不相关信息，影响后续模型判断。

#### 问：prompt injection 是什么

答：

用户输入或外部文档中包含恶意指令，试图覆盖系统提示或改变 Agent 行为。

### 32.9 RAG 扩展八股

#### 问：embedding 模型和生成模型一定要同一家吗

答：

不一定。embedding 更关注语义检索质量，生成模型更关注回答能力，两者可以分开选。

#### 问：为什么 chunk 不能只按固定字数切

答：

因为会破坏语义完整性，导致检索命中的是半句、半段或上下文残缺内容。

#### 问：重排序 rerank 是什么

答：

先用向量检索粗召回，再用更强的相关性模型对候选结果重排，提高最终上下文质量。

---

## 33. 场景设计题和延伸问题

这一节是很多技术面后半段会问的“如果让你继续做，会怎么设计”。

### 33.1 如果要支持流式输出，你怎么改

建议回答：

`后端我会把 `/api/agent/chat` 从完整响应扩展成 SSE 或 WebSocket 形式，模型输出按 token 或 chunk 推送；前端页面则改成增量渲染消息气泡。工具调用阶段要区分“模型思考流”和“工具执行结果流”，状态机会比现在复杂。`

### 33.2 如果 thread 很长，上下文怎么办

建议回答：

`现在我只是简单限制最近消息数量，如果继续做，我会考虑做摘要压缩、分层记忆或者只保留关键事实和最近轮次，避免上下文无限增长。`

### 33.3 如果多个用户同时用这个系统怎么办

建议回答：

`当前项目还没有多租户和权限体系，真正扩展时要补 user、tenant、权限校验和资源隔离。数据表里很多对象都要增加 user_id 或 tenant_id。`

### 33.4 如果 provider 经常超时怎么办

建议回答：

`可以做三层优化：第一是更细的超时和重试策略；第二是 provider fallback；第三是把超时和失败率暴露成监控指标，便于做动态路由和熔断。`

### 33.5 如果工具很多，模型选错工具概率高怎么办

建议回答：

`我会减少同类工具的重叠，优化工具描述，必要时把工具分组或分 Agent 域，而不是把几十个工具一次性全暴露给一个 Agent。`

### 33.6 如果 job 被重复提交怎么办

建议回答：

`当前项目没有做强幂等控制，如果生产化，我会考虑引入请求指纹、去重 key，或者按 thread / 内容 / 参数组合作幂等判断。`

### 33.7 如果内容量很大，SQLite 顶不住怎么办

建议回答：

`先切 PostgreSQL，再看查询模式是否要把 tags、tool events、metrics 做更细的表结构或 JSONB。SQLite 适合 demo，本来就不是最终并发方案。`

### 33.8 如果要做线上监控，你会加什么

建议回答：

- 接口耗时
- provider 成功率和超时率
- tool 调用成功率
- job 排队长度
- thread 平均长度
- 常见错误码

### 33.9 如果要做评测体系，你会怎么设计

建议回答：

`我会分三层。第一层是契约测试，确保接口和状态结构不乱；第二层是固定输入输出的回归测试，防止 prompt 改动带来明显退化；第三层是业务评测，比如工具调用成功率、用户任务完成率、内容质量人工打分。`

---

## 34. 针对简历的技术细节自查表

这部分是给你面试前最后一轮自查用的。

### 34.1 AI Content Ops Agent Platform

你必须能回答：

- 四阶段 Agent 每一步输入输出是什么
- 9 个工具分别做什么
- provider 路由怎么做
- 为什么 job 要落库
- 为什么 tool_events 要持久化
- 为什么要区分 Workflow Agent 和 Chat Agent
- 为什么测试里不用真实模型

### 34.2 Django / RAG 实习

你必须能回答：

- Django 项目是前后端一体还是接口模式
- RAG 的文档从哪里来
- 文档怎么清洗
- chunk 怎么切
- 检索错了会怎样
- Docker 怎么跑起来

### 34.3 多模态项目

你必须能回答：

- 输入是什么
- 标签怎么来
- 指标怎么计算
- 你真正负责的模块是什么
- 轻量化做了什么

### 34.4 AI 编程工具和 skills

你必须能回答：

- 你具体怎么用 Claude Code / Cursor / Codex
- 是拿来生成代码、改 bug、补测试还是写文档
- 你说的 skills 到底是什么
- 它解决了什么效率问题

---

## 35. 建议你额外手写的两份材料

除了这份文档，建议你自己再手写两份简版材料。

### 35.1 一页纸项目图

内容包括：

- 前端页面
- API 路由
- service 分层
- LiteLLM
- LangChain tool calling
- SQLAlchemy 持久化
- job queue

你不用画得漂亮，但一定要自己画一遍。

### 35.2 一页纸术语速记

把下面这些词写在一页纸上，考前过一遍：

- `ASGI`
- `Uvicorn`
- `Starlette`
- `Pydantic`
- `Depends`
- `WAL`
- `Session`
- `flush / commit`
- `StructuredTool`
- `tool_calls`
- `ToolMessage`
- `LiteLLM`
- `provider fallback`
- `polling`
- `SSE`
- `RAG`
- `chunking`
- `embedding`
- `rerank`

---

## 36. 框架底层深挖版

这一节是专门给喜欢抓“底层机制”的面试官准备的。你不需要把源码背下来，但要能把运行链路讲通。

### 36.1 FastAPI / Starlette / Uvicorn 深挖

#### 36.1.1 ASGI 到底是什么

安全且够深的回答：

`ASGI 是 Python 异步 Web 应用的通用调用规范，可以理解成 Web 服务器和应用之间的接口协议。一个 ASGI app 本质上是一个接收 scope、receive、send 的可调用对象。scope 描述连接上下文，receive 用来接收事件，send 用来发送事件。相比 WSGI，ASGI 能原生支持异步、长连接、WebSocket 和更高并发的 IO 场景。`

#### 36.1.2 请求从浏览器到 FastAPI 的真实路径

可以这样答：

`浏览器先发 HTTP 请求给 Uvicorn，Uvicorn 作为 ASGI server 负责监听端口、解析协议、建立连接，然后把请求转换成 ASGI 事件流，再交给 FastAPI。FastAPI 实际上是建立在 Starlette 之上的，所以路由匹配、中间件执行、Request/Response 包装很多都是 Starlette 在做，Pydantic 则主要负责数据校验和序列化。`

#### 36.1.3 `async def` 和 `def` 在 FastAPI 里怎么执行

这是高频深挖题。

推荐回答：

`如果路由函数是 async，FastAPI 会直接在事件循环里调度；如果是普通 def，同步函数通常会被放到线程池里执行，避免阻塞事件循环。所以不是所有接口都必须写成 async，关键是看里面是否有大量 IO 等待。`

注意：

- 这个回答比“async 就更快”更专业。
- 面试官如果追问线程池，你就说“框架会帮助把同步阻塞逻辑隔离到线程池执行，避免卡住主事件循环”。

#### 36.1.4 中间件执行顺序

推荐回答：

`请求进入时是按注册顺序一层层进入中间件，再到具体路由；响应返回时则按相反顺序回退。`

你项目里可结合说：

`我这里主要用的是 CORS middleware，放在 app 层统一处理跨域。`

#### 36.1.5 FastAPI 为什么能自动生成接口文档

推荐回答：

`因为它会读取路由函数签名、Pydantic schema、response_model 和状态码信息，生成 OpenAPI 描述，然后自动暴露 Swagger UI 和 ReDoc。`

#### 36.1.6 依赖注入的执行时机

推荐回答：

`在真正调用路由函数之前，FastAPI 会先解析函数签名，发现 Depends 后先执行依赖函数，把返回值注入进来。如果依赖本身还有 Depends，就会递归解析。`

#### 36.1.7 为什么 `get_store` 用 `lru_cache`

推荐回答：

`因为 store 里持有数据库 engine 和 session factory，这类对象适合在进程内复用，而不是每次请求重建。用 lru_cache 可以保证整个进程里只初始化一次。`

#### 36.1.8 为什么你没有用 FastAPI 的 lifespan

安全回答：

`这个项目规模还不大，依赖对象也比较简单，所以我先用了 lru_cache 和普通依赖函数。如果继续扩展，比如需要统一管理启动时资源、连接池、监控或清理逻辑，我会考虑用 lifespan。`

### 36.2 Pydantic 深挖

#### 36.2.1 Pydantic 做的不只是类型提示

推荐回答：

`类型注解只是声明，真正让它生效的是 Pydantic。请求 JSON 进来后，Pydantic 会做字段存在性校验、类型转换、枚举校验、范围校验和默认值填充，最后再生成一个结构化对象传给业务层。`

#### 36.2.2 你项目里 schema 设计体现在哪

具体例子：

- `GenerateRequest.topic` 要求 `min_length=1`
- `RefineRequest.content_id` 要求 `gt=0`
- `temperature` 要求 `0.0 <= x <= 1.0`
- `max_tokens` 要求 `128 <= x <= 8192`
- `length` 用 `Literal["short", "medium", "long"]`
- `content_type` 和 `style` 用 `Enum`

你可以总结成：

`我在 schema 层尽量把可预见的输入错误提前拦掉，这样业务层接收到的数据更干净。`

#### 36.2.3 为什么 `422` 不是业务错误

推荐回答：

`422 表示结构和字段值本身不符合 schema，是输入层错误；像 provider 不存在、内容 ID 查不到这类是业务语义错误，更适合返回 400 或 404。`

### 36.3 Vue3 响应式系统深挖

#### 36.3.1 Vue3 响应式的核心数据结构

你可以答到这个层次：

`Vue3 的响应式核心可以理解成一个依赖收集图。读取 reactive 对象属性时会 track，把当前活跃副作用收集到依赖表里；修改属性时会 trigger，把相关副作用重新调度执行。底层常见的数据结构思路是 WeakMap -> Map -> Set，也就是对象到属性到 effect 的映射。`

#### 36.3.2 为什么 `computed` 有缓存

推荐回答：

`因为 computed 本质上是带缓存和脏标记的惰性 effect。依赖不变时再次读取会直接返回旧值，依赖变了才会标记为 dirty，等下次访问时再重新计算。`

#### 36.3.3 `watch` 为什么适合副作用

推荐回答：

`因为 watch 关注的是‘变化之后要做什么’，常见场景是发请求、写日志、同步外部状态；computed 关注的是‘基于已有状态派生出什么值’。`

#### 36.3.4 Vue 为什么不是一改数据就立刻更新 DOM

推荐回答：

`Vue 会把同一轮事件循环里的多个状态变更合并进调度队列做批量更新，避免频繁重复渲染。真正拿到更新后的 DOM 通常要等到 nextTick。`

#### 36.3.5 `v-model` 在组件上是怎么工作的

结合你的 `ModelSelector` 说：

`本质上是父组件传入一个值，子组件通过 `update:modelValue` 事件把变化回传。我的 `ModelSelector` 是受控组件模式，内部维护 local 状态，再通过 watch 和 emit 同步给父组件。`

### 36.4 SQLAlchemy 深挖

#### 36.4.1 Session 不是连接

推荐回答：

`Session 更像 ORM 的工作单元，负责对象状态管理和事务边界；真正的数据库连接由 Engine 和连接池管理。`

#### 36.4.2 Unit of Work 是什么

可以答到概念层：

`SQLAlchemy 的 Session 会跟踪对象状态变化，把一批改动统一 flush/commit，这就是 Unit of Work 思路。`

#### 36.4.3 为什么每个 store 方法都自己开关 session

推荐回答：

`因为这个项目规模不大，我选择了短会话模式，每次操作自己控制事务边界、异常回滚和 session close。这样简单直接，也比较不容易把 session 泄漏到各层。`

#### 36.4.4 为什么 `update_job` 能自动补 `started_at` 和 `completed_at`

推荐回答：

`这体现的是状态机思路。job 一旦从 queued 进入 running，就补 started_at；一旦进入 completed 或 failed，就补 completed_at。这样前端和运维侧都更容易观察任务生命周期。`

### 36.5 SQLite 深挖

#### 36.5.1 WAL 为什么对这个项目有帮助

推荐回答：

`WAL 模式下读和写的冲突会比传统 rollback journal 模式更少，更适合我这种读操作较多、偶尔有后台写任务的场景。`

#### 36.5.2 `busy_timeout` 解决什么问题

推荐回答：

`SQLite 并发写能力有限，如果数据库暂时被占用，busy_timeout 可以让连接多等一会儿，而不是立刻抛 database is locked。`

#### 36.5.3 为什么 SQLite 不适合最终高并发

推荐回答：

`它适合轻量单机和 demo，不适合很多写请求并发的生产系统，所以项目里也预留了 PostgreSQL + Redis + RQ 方案。`

### 36.6 Redis / RQ 深挖

#### 36.6.1 RQ worker 是怎么工作的

安全回答：

`RQ worker 会持续从 Redis 队列取任务，反序列化任务内容，然后执行指定的 Python 函数。我的项目里这个函数就是 `src.jobs.runner.run_job`。`

#### 36.6.2 为什么 job 不直接执行 service，而要先构造成 request schema

推荐回答：

`因为 job payload 落库后本质上是普通 JSON 数据，重新构造成 `GenerateRequest`、`AgentRunRequest` 这些 schema，可以复用同一套校验和业务逻辑，避免 job runner 变成另一套平行实现。`

#### 36.6.3 为什么 job 有 `attempts`

推荐回答：

`一方面便于观察任务是否多次执行，另一方面也为未来重试策略预留空间。`

### 36.7 Axios / 前端工程深挖

#### 36.7.1 为什么 `ApiError` 要保存 `status` 和 `detail`

推荐回答：

`message 适合直接展示给用户，status 和 detail 则保留给页面逻辑或调试使用。比如 429 和 502 在产品层面应该有不同提示。`

#### 36.7.2 为什么 baseURL 写成 `/api`

推荐回答：

`因为开发态走 Vite 代理，生产态也可以通过统一前缀把前后端 API 路径隔离开。`

---

## 37. 项目数据模型、字段约束、状态机

这一节专门准备“你这个表怎么设计的”“为什么字段这么配”“状态如何流转”。

### 37.1 ContentType 和 ContentStyle 为什么用 Enum

真实枚举值：

- `ContentType`
  `xiaohongshu`
  `weibo`
  `blog`
  `video_script`
  `twitter`

- `ContentStyle`
  `professional`
  `casual`
  `marketing`
  `storytelling`

为什么用 Enum：

- 限制非法值
- 前后端语义统一
- Pydantic 自动校验

### 37.2 Generate / Refine / Title / SEO 四类 request 的区别

你要能说明：

- `GenerateRequest` 面向新内容生成
- `RefineRequest` 面向已有内容二次加工
- `TitleRequest` 既可以基于 topic，也可以基于 content_id
- `SeoRequest` 只针对已保存内容

这说明你的接口不是胡乱堆功能，而是有明确职责划分。

### 37.3 Content 表字段设计

关键字段：

- `title`
- `content`
- `content_type`
- `style`
- `keywords`
- `tags`
- `status`
- `version`
- `parent_id`
- `llm_provider`
- `model_name`
- `token_usage`
- `cost_estimate`

你可以解释几个典型字段：

- `parent_id`：为改写版本、衍生版本预留链路
- `status`：区分 draft、refined、agent_final 等状态
- `llm_provider` / `model_name`：保留生成来源，便于追踪
- `keywords` / `tags`：区分用户输入关键词和模型产出标签

### 37.4 AgentThread 和 AgentMessage 为什么分表

推荐回答：

`thread 是会话级元数据，message 是消息级数据，两者生命周期和查询粒度不同，所以拆表更自然。thread 主要看最后使用模型、更新时间和消息数；message 主要存具体文本和 tool events。`

### 37.5 Job 表为什么自己设计而不是只依赖 RQ 状态

推荐回答：

`因为 job 不只是队列任务，它还是前端页面可观察的业务状态。自己设计 job 表之后，BackgroundTasks 和 RQ 两种模式都能共用同一套状态查询接口。`

### 37.6 状态机要能讲顺

内容状态至少要能说：

- `draft`
- `refined`
- `agent_final`

job 状态至少要能说：

- `queued`
- `running`
- `completed`
- `failed`

Agent step 状态至少要能说：

- `pending`
- `running`
- `completed`
- `failed`

### 37.7 版本关系怎么理解

你项目里 refine 会生成新内容，而不是覆盖旧内容，所以可以讲成：

`我更倾向把改写理解成派生版本，因此不是 update 原记录，而是保留父子关系，方便回溯和版本管理。`

### 37.8 `parse_generated_content` 的实现和风险

这是一个很适合表现你有工程意识的点。

实现思路：

- 先统一换行符
- 再用正则提取标题、正文、标签
- 解析失败时回退到原始文本

可主动说出的风险：

- 强依赖输出格式约定
- 如果模型格式漂移，解析会变脆弱
- 更稳的生产方案可以考虑 function calling 或更严格的结构化输出

---

## 38. 测试矩阵和如何讲测试

这一节专门帮助你回答“你到底测了什么，怎么测的”。

### 38.1 当前测试文件都覆盖了什么

`tests/test_api_contract.py`

- health check
- agent chat 持久化
- tool events 保存
- thread 接口
- models 接口
- generate 请求校验
- generate 错误映射
- generate 持久化
- agent pipeline 成功
- agent pipeline 失败步骤回传

`tests/test_jobs_contract.py`

- content generation job 成功
- agent run job 成功
- provider inflight 限流返回 `429`

`tests/test_config_contract.py`

- provider model name 前缀映射
- claude 模型名不改写
- 非法 provider 报错
- timeout 配置为正值

`tests/test_content_parsing.py`

- 生成内容格式解析
- 换行兼容
- 解析失败时回退逻辑

`tests/test_storage_stats.py`

- 内容统计接口对动态状态的处理

### 38.2 为什么说这是 contract test

推荐回答：

`因为我更多验证的是接口行为、响应结构和状态流转，而不是某个内部函数的实现细节。`

### 38.3 为什么不用真实 provider 做默认测试

推荐回答：

`真实模型结果不稳定、耗时、依赖网络，也会消耗额度，所以默认测试更适合用 fake client 做可重复验证。`

### 38.4 如果面试官问“你怎么保证 prompt 改了不退化”

可以答：

`当前项目主要保证的是接口和流程稳定，如果要进一步做 prompt 回归，我会补固定输入输出的回归 case 和人工评测集。`

### 38.5 mock 和 fake 的区别

安全回答：

`mock 更偏替换行为并验证调用；fake 更像一个可运行的轻量实现。我的 FakeLLMClient 和 FakeChatModel 更接近 fake。`

---

## 39. 性能、稳定性、安全性、可扩展性

这一节是很多较强的面试官会问的。

### 39.1 性能上当前方案的优点

- 前后端解耦
- LLM 调用走 async
- 长任务支持异步队列
- SQLite 开了 WAL
- 前端路由懒加载

### 39.2 性能上当前方案的瓶颈

- SQLite 并发写能力有限
- 轮询有额外请求开销
- tool calling 仍然串行执行
- Chat Agent 历史消息简单截断，不够智能

### 39.3 稳定性措施

- LLM 超时控制
- route 层明确错误映射
- job 状态落库
- tool loop 有最大轮数限制
- provider inflight job 限流
- fake 测试覆盖核心流程

### 39.4 安全性不足

你可以主动承认这些还没做：

- 没有认证鉴权
- 没有权限隔离
- 没有严格的输入审计
- 没有 prompt injection 防护
- 没有速率限制

### 39.5 如果面试官问 prompt injection 怎么防

建议回答：

`可以从三层做。第一层是系统提示和工具权限约束；第二层是对外部文档或用户输入做过滤和降权，不轻易把它们当作高优先级指令；第三层是把高风险工具做白名单和参数校验，不能完全相信模型生成的调用参数。`

### 39.6 如果面试官问如何做日志

建议回答：

`我会区分三类日志：接口访问日志、Agent 运行日志、工具执行日志。对 Agent 来说，thread_id、run_id、provider、model、step_id、job_id 都是很重要的关联字段。`

### 39.7 如果面试官问如何做监控告警

建议回答：

`我会先监控 provider 超时率、接口错误率、job 排队长度、tool failure rate 和平均任务耗时，再按阈值做告警。`

### 39.8 如果面试官问未来怎么拆服务

建议回答：

`当前是单体应用，后续如果复杂度上来，可以先把 job worker 独立，再把模型路由或内容服务拆开，但在当前阶段单体更利于快速迭代和统一状态管理。`

---

## 40. 技术面连续追问模板

这一节给你的是“面试官一层层追问时怎么答”。

### 40.1 关于 FastAPI 的连续追问

第一问：

`为什么用 FastAPI？`

第一层回答：

`因为它更适合接口驱动项目，Pydantic 校验、依赖注入和 async 支持都比较好。`

第二问：

`那 async 到底快在哪？`

第二层回答：

`快的不是 CPU，而是等待 IO 时不阻塞线程，尤其适合这种要请求大模型 API 的场景。`

第三问：

`如果是同步 def 呢？`

第三层回答：

`同步函数通常会交给线程池执行，避免阻塞主事件循环。`

第四问：

`那你为什么数据库层还是同步的？`

第四层回答：

`这个项目规模还不大，优先用了实现更简单的同步 ORM；如果并发继续提高，可以切 async engine。`

### 40.2 关于 LiteLLM 的连续追问

第一问：

`为什么要 LiteLLM？`

第一层回答：

`统一多 provider 接口，减少业务层和具体模型 SDK 的耦合。`

第二问：

`那为什么还要自己封装 LiteLLMClient？`

第二层回答：

`因为我还想统一处理 key、base_url、超时和异常，不希望业务层到处写重复逻辑。`

第三问：

`不同 provider 模型名为什么不一样？`

第三层回答：

`LiteLLM 虽然统一接口，但 provider 仍然有自己的命名约定，所以我在 config 层做了模型名前缀映射。`

### 40.3 关于 LangChain 的连续追问

第一问：

`你为什么用 LangChain？`

第一层回答：

`主要是为了 message abstraction 和 tool calling。`

第二问：

`那为什么不用它做全部工作流？`

第二层回答：

`因为四阶段 pipeline 本身不复杂，我更想自己控制状态、错误处理和持久化。`

第三问：

`如果工具调用出错呢？`

第三层回答：

`我会把错误封装成 tool event，并继续作为 ToolMessage 回传，避免整个线程直接失控。`

### 40.4 关于 SQLAlchemy 的连续追问

第一问：

`为什么用 SQLAlchemy？`

第一层回答：

`因为我需要持久化多类结构化状态，ORM 更适合快速建模。`

第二问：

`Session 是什么？`

第二层回答：

`是 ORM 的工作单元，不是数据库连接本身。`

第三问：

`commit 和 flush 区别？`

第三层回答：

`flush 先把改动发到数据库但事务未提交，commit 才是真正提交。`

第四问：

`为什么 SQLite 还敢做 job 状态？`

第四层回答：

`因为当前定位是 demo 和轻量场景，并且开了 WAL 和 busy timeout；真正高并发会切 PostgreSQL。`

### 40.5 关于 Vue3 的连续追问

第一问：

`为什么用 Vue3？`

第一层回答：

`开发效率高，Composition API 很适合组织复杂页面状态。`

第二问：

`响应式底层是什么？`

第二层回答：

`Proxy + effect，读取时 track，修改时 trigger。`

第三问：

`computed 为什么有缓存？`

第三层回答：

`因为它是带 dirty 标记的惰性 effect。`

第四问：

`为什么你的 ModelSelector 要本地复制一份 props？`

第四层回答：

`因为它是受控组件，要兼顾父组件外部更新和内部交互编辑，所以用了本地 reactive 状态再双向同步。`

### 40.6 关于 Agent 的连续追问

第一问：

`Workflow Agent 和 Chat Agent 区别？`

第一层回答：

`一个偏固定流程，一个偏开放式工具调用。`

第二问：

`为什么不全部做成 Chat Agent？`

第二层回答：

`因为固定内容生产任务更适合显式步骤编排，可控性和可解释性更强。`

第三问：

`为什么不全部做成固定 pipeline？`

第三层回答：

`因为开放式任务需要根据用户意图灵活决策是否调用工具，固定 pipeline 会过于僵硬。`

第四问：

`那你这个 Agent 真的智能吗？`

第四层回答：

`我不会把它包装成强自治智能体，它更像受约束的任务型 Agent，核心价值在于工作流闭环、工具执行和状态追踪。`

