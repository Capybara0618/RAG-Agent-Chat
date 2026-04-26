from __future__ import annotations

import json
import os
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MethodType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.core.config import build_settings
from app.main import create_app
from app.services.retrieval.rerankers import _select_top_chunks


RUNTIME_ROOT = Path("tmp_eval_legal_ablation")
EMBEDDING_MODEL_PATH = Path(r"D:\Models\BAAI\bge-base-zh-v1___5")
RERANKER_MODEL_PATH = Path(r"D:\Models\bge-reranker-base")
DEFAULT_PIPELINES = ("bm25_only", "semantic_only", "hybrid_rrf", "hybrid_rrf_rerank")
LEGAL_DOC_PREFIX = "法务核心-"

LEGAL_KB_FILES = [
    (
        "法务核心-合同审查红线指引.md",
        """# 合同审查红线指引

## 核心红线
责任上限、赔偿责任、审计权、数据处理、保密义务、安全事件通知、便利终止原则上不得删除或明显弱化。

## 审查要求
若对方坚持删除或弱化核心红线条款，应退回采购重新沟通，并由法务人工确认是否接受偏离。
""",
    ),
    (
        "法务核心-标准主服务协议模板.md",
        """# 标准主服务协议模板

## 责任上限
供应商在本协议项下的累计责任上限原则上不低于过去十二个月已收取服务费总额。

## 赔偿责任
供应商应就其违约、侵权、数据处理不当造成的损失承担赔偿责任。

## 审计权
如供应商处理我方业务数据，我方有权在合理通知后开展审计或要求提供审计证明。

## 数据处理
供应商仅可根据我方书面指示处理数据，未经同意不得跨境传输，不得擅自变更处理目的。

## 保密义务
供应商对我方保密信息负有持续保密义务，未经书面许可不得向第三方披露。

## 安全事件通知
发生已确认的安全事件后，供应商应在二十四小时内通知我方。

## 便利终止
我方有权基于业务调整需要提前书面通知解除合同。
""",
    ),
    (
        "法务核心-数据处理供应商检查清单.md",
        """# 数据处理供应商检查清单

## 高风险信号
出现以下任一情形时，应视为重点风险并升级法务复核：
1. 允许供应商按运营需要自行跨境传输数据。
2. 允许供应商自行安排分包或子处理且无需我方书面同意。
3. 不承诺固定的安全事件通知时限。
4. 允许供应商改变处理目的或扩大数据使用范围。
""",
    ),
    (
        "法务核心-争议解决补充说明.md",
        """# 争议解决补充说明

## 常见关注点
若对方要求适用境外法律、境外仲裁地或由供应商所在地法院专属管辖，应视为法务观察项，并结合项目重要性判断是否接受。
""",
    ),
    (
        "法务核心-付款条款审查要点.md",
        """# 付款条款审查要点

## 审查原则
付款周期明显延长、要求大额预付款、设置过高逾期违约金时，应作为法务观察项并联动采购确认商业合理性。
""",
    ),
    (
        "法务核心-服务水平与违约责任要点.md",
        """# 服务水平与违约责任要点

## 服务水平
供应商不应完全删除服务水平承诺或服务赔偿机制；若仅保留“尽力而为”表述，应提示业务和法务进一步确认。
""",
    ),
    (
        "法务核心-小额试点采购例外审批说明.md",
        """# 小额试点采购例外审批说明

## 适用范围
仅适用于预算不超过五万元、合同周期不超过三个月、且不处理客户业务数据的小额试点项目。

## 例外情形
在完成管理层书面审批后，可接受少量预付款、简化服务水平承诺或以供应商年度自评报告作为补充材料。

## 限制条件
本说明不得作为删除责任上限、赔偿责任、审计权或数据处理条款的通用依据。
""",
    ),
    (
        "法务核心-境外部署项目合同例外备忘录.md",
        """# 境外部署项目合同例外备忘录

## 场景说明
当项目明确属于境外部署、境外主体签约或需遵守当地监管要求时，可就适用法律、争议解决地或数据跨境路径讨论例外方案。

## 审批要求
如需接受境外法律、境外仲裁地或跨境传输安排，必须补充项目背景、数据范围、合规措施并完成专项审批。

## 注意事项
该备忘录不意味着一般国内 SaaS 采购可直接接受境外法律或默认开放跨境数据传输。
""",
    ),
    (
        "法务核心-服务商自评材料接收说明.md",
        """# 服务商自评材料接收说明

## 材料接收原则
对于尚未处理客户核心数据的供应商，可先接收其年度自评报告、渗透测试摘要或第三方认证作为前置材料。

## 风险提示
自评材料仅可作为补充参考，原则上不能直接替代合同中的审计权、通知义务或数据处理条款。
""",
    ),
    (
        "法务核心-实施服务验收补充条款.md",
        """# 实施服务验收补充条款

## 付款安排
对于实施周期较长的项目，可按里程碑分期付款；如供应商要求预付款，应说明商业必要性并与采购确认合理区间。

## 验收关联
付款节点应与上线、验收、运维支持等交付里程碑相匹配，避免出现高比例预付款且缺少履约约束。
""",
    ),
    (
        "法务核心-保密信息共享例外场景.md",
        """# 保密信息共享例外场景

## 可讨论的有限例外
在融资、审计、并购或集团内部合规审查场景下，经双方书面确认后，可向特定顾问或关联方披露必要保密信息。

## 使用边界
该例外仅适用于特定场景，不代表供应商可在一般服务运营过程中自由向合作伙伴披露客户或业务信息。
""",
    ),
    (
        "法务核心-市场合作协议审查提示.md",
        """# 市场合作协议审查提示

## 常见关注点
市场合作、渠道推广或联合品牌活动协议通常更关注宣传口径、品牌授权、费用结算和责任划分。

## 与采购合同差异
若项目本质是软件采购或数据处理服务，应以采购类合同红线和主服务协议模板为主要依据，而非市场合作条款习惯。
""",
    ),
    (
        "法务核心-数据迁移项目特别说明.md",
        """# 数据迁移项目特别说明

## 特别风险
数据迁移项目可能涉及临时子处理方、过渡期跨环境访问和分阶段删除要求，应明确迁移范围、迁移期限和回收机制。

## 审查边界
即使存在迁移安排，也不代表可以长期保留“按运营需要跨境传输”或“供应商自行安排分包”一类表述。
""",
    ),
    (
        "法务核心-历史争议案例摘要.md",
        """# 历史争议案例摘要

## 案例一
因合同仅约定“合理时间内通知安全事件”，导致采购方无法及时响应客户投诉，后续补充明确时限。

## 案例二
因责任上限被压缩至短周期服务费，争议发生后采购方损失覆盖不足。

## 提示
案例仅用于辅助理解风险，不直接替代现行制度或模板要求。
""",
    ),
    (
        "法务核心-框架合作协议付款安排参考.md",
        """# 框架合作协议付款安排参考

## 参考做法
年度框架合作协议下可按季度结算，也可在订单层面约定预付款、验收款和质保金，但需结合业务属性判断。

## 风险边界
若基础服务尚未交付即要求高比例预付款，或付款节点明显偏离行业惯例，仍需纳入法务观察项。
""",
    ),
    (
        "法务核心-信息安全配合与证据提供说明.md",
        """# 信息安全配合与证据提供说明

## 证据配合
供应商可通过安全白皮书、渗透测试报告、认证证书和整改记录等材料辅助证明安全能力。

## 与合同条款关系
前述材料仅能辅助证明安全现状，不能替代合同中的安全事件通知、审计配合或数据处理义务。
""",
    ),
    (
        "法务核心-验证性项目供应商审查说明.md",
        """# 验证性项目供应商审查说明

## 适用场景
适用于预算较小、周期较短、仅供内部团队试运行验证、且原则上不接触正式客户或生产业务数据的项目。

## 可讨论边界
在完成试运行立项或管理审批后，可讨论适度预付款、弱化量化 SLA、以第三方安全材料配合替代部分现场核查安排。

## 不适用情形
若项目会处理正式客户数据、形成对外服务能力或长期商用，则仍应回到标准采购合同和核心红线要求。
""",
    ),
    (
        "法务核心-国际业务合同变更处理说明.md",
        """# 国际业务合同变更处理说明

## 适用场景
当项目服务对象主要位于境外、签约主体为海外关联公司，且系统部署、运维和争议处理均需贴合当地监管要求时，可评估境外法律或境外争议解决安排。

## 审查要点
如需接受境外法律、境外仲裁地或跨境数据访问，应同时补充业务必要性、数据流向、主体关系和专项审批结论。

## 风险边界
对普通境内 SaaS 采购，不应仅因供应商习惯而默认接受境外法律或开放式跨境传输条款。
""",
    ),
    (
        "法务核心-阶段性数据迁移控制说明.md",
        """# 阶段性数据迁移控制说明

## 适用场景
对于历史工单、存量台账或归档数据的阶段性迁移项目，可在明确迁移窗口、删除时限和责任分工后评估临时中转或受控访问安排。

## 控制要求
迁移结束后应及时删除临时副本，不得把阶段性迁移安排写成长期运营中的常态化开放权限。

## 风险边界
若合同表述允许供应商按运营需要持续跨境处理或自行扩大处理目的，仍应视为高风险。
""",
    ),
    (
        "法务核心-第三方安全证明材料适用说明.md",
        """# 第三方安全证明材料适用说明

## 可接受材料
供应商可提交年度审计报告、认证证书、渗透测试摘要或整改记录，作为其安全能力的辅助证明。

## 使用边界
前述材料更适合低风险、试运行或暂未承载正式客户数据的场景，用于降低前期尽调成本。

## 风险边界
如合同已经涉及正式客户数据、持续运营或关键业务支撑，仅以自评或第三方材料替代合同审计权通常并不充分。
""",
    ),
    (
        "法务核心-关联方协同披露限制说明.md",
        """# 关联方协同披露限制说明

## 有限例外
在融资、集团合规审查、外部审计或并购尽调等有限场景下，经书面确认后可向特定顾问或关联主体披露必要保密信息。

## 使用边界
上述例外应限定在明确目的、特定对象和最小必要范围内，不宜写成供应商可为一般运营目的自由共享业务信息。
""",
    ),
    (
        "法务核心-分阶段付款与试运行安排说明.md",
        """# 分阶段付款与试运行安排说明

## 适用场景
对实施周期明确、需要供应商先投入配置或部署资源的试运行项目，可讨论少量预付款与里程碑验收结合的付款安排。

## 审查要点
应同步说明交付里程碑、验收标准和预付款比例，不宜出现高比例预付款且缺少履约约束。

## 风险边界
若项目属于正式商用采购、金额较大或长期运行，仍应优先采用标准付款节奏。
""",
    ),
]


@dataclass(frozen=True)
class LegalEvalCase:
    name: str
    expected_decision: str
    expected_risk: str
    acceptable_titles: tuple[str, ...]
    expected_clauses: tuple[str, ...]
    our_contract_name: str
    counterparty_contract_name: str
    our_contract: str
    counterparty_contract: str
    primary_titles: tuple[str, ...] = ()
    project_title: str = "法务评测-客服SaaS采购"
    department: str = "客户服务部"
    category: str = "customer-support-saas"
    budget_amount: float = 580000
    summary: str = "采购客服 SaaS，进入法务合同审查。"
    business_value: str = "统一客服流程并降低响应时长。"
    data_scope: str = "customer_data"


LEGAL_EVAL_CASES = [
    LegalEvalCase(
        name="severe_redline",
        expected_decision="return",
        expected_risk="high",
        acceptable_titles=("法务核心-合同审查红线指引.md", "法务核心-标准主服务协议模板.md", "法务核心-数据处理供应商检查清单.md"),
        expected_clauses=("责任上限", "审计权", "数据处理", "安全事件通知"),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-严重红线版.md",
        our_contract="""# 我方采购合同

## 核心条款
责任上限原则上不低于过去十二个月已收取服务费总额。
供应商应承担赔偿责任。
我方保留审计权。
供应商仅可根据我方书面指示处理数据，未经同意不得跨境传输。
发生安全事件后，供应商应在二十四小时内通知我方。
供应商对我方保密信息负有持续保密义务。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 核心条款
责任上限调整为不超过三个月服务费总额。
供应商仅退还已收费用，不承担其他赔偿责任。
供应商可根据运营需要将服务数据传输至其关联部署地点，并可自行安排分包。
发生安全事件后，供应商将在合理可行范围内尽快通知，但不承诺固定通知时限。
供应商可向合作方披露业务信息用于服务运营。
""",
    ),
    LegalEvalCase(
        name="mostly_clean_watch_item",
        expected_decision="approve",
        expected_risk="medium",
        acceptable_titles=("法务核心-标准主服务协议模板.md", "法务核心-争议解决补充说明.md", "法务核心-付款条款审查要点.md"),
        expected_clauses=("付款条款", "争议解决与适用法律"),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-轻微修改版.md",
        our_contract="""# 我方采购合同

## 核心条款
责任上限原则上不低于过去十二个月已收取服务费总额。
我方保留审计权。
供应商仅可根据我方书面指示处理数据。
发生安全事件后，供应商应在二十四小时内通知我方。
供应商对我方保密信息负有持续保密义务。
争议解决适用中华人民共和国法律，由我方所在地法院管辖。
付款期限为验收后三十日。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 核心条款
责任上限原则上不低于过去十二个月已收取服务费总额。
我方保留审计权。
供应商仅可根据我方书面指示处理数据。
发生安全事件后，供应商应在二十四小时内通知我方。
供应商对我方保密信息负有持续保密义务。
争议解决适用中华人民共和国法律，由供应商所在地法院管辖。
付款期限为验收后四十五日。
""",
    ),
    LegalEvalCase(
        name="data_processing_risk",
        expected_decision="return",
        expected_risk="high",
        acceptable_titles=("法务核心-数据处理供应商检查清单.md", "法务核心-标准主服务协议模板.md"),
        expected_clauses=("数据处理", "分包限制", "安全事件通知"),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="供应商数据处理回传版.md",
        our_contract="""# 我方采购合同

## 数据与安全条款
供应商仅可根据我方书面指示处理数据，未经同意不得跨境传输。
发生安全事件后，供应商应在二十四小时内通知我方。
我方保留审计权。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 数据与安全条款
供应商可根据运营需要将服务数据传输至境外关联部署地点。
供应商可自行安排子处理方提供服务，无需逐次取得我方书面同意。
发生安全事件后，供应商将在合理可行范围内尽快通知。
""",
    ),
    LegalEvalCase(
        name="confidentiality_removed",
        expected_decision="return",
        expected_risk="high",
        acceptable_titles=("法务核心-合同审查红线指引.md", "法务核心-标准主服务协议模板.md"),
        expected_clauses=("保密义务",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-保密删除版.md",
        our_contract="""# 我方采购合同

## 保密条款
供应商对我方保密信息负有持续保密义务，未经书面许可不得向第三方披露。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 保密条款
双方可在业务合作需要时向关联方或合作伙伴披露相关信息，无需另行征得对方同意。
""",
    ),
    LegalEvalCase(
        name="convenience_termination_removed",
        expected_decision="return",
        expected_risk="high",
        acceptable_titles=("法务核心-合同审查红线指引.md", "法务核心-标准主服务协议模板.md"),
        expected_clauses=("便利终止",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-终止限制版.md",
        our_contract="""# 我方采购合同

## 终止条款
我方有权基于业务调整需要提前书面通知解除合同。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 终止条款
除非供应商发生重大违约，否则我方不得提前解除合同。
""",
    ),
    LegalEvalCase(
        name="sla_softened_only",
        expected_decision="approve",
        expected_risk="medium",
        acceptable_titles=("法务核心-服务水平与违约责任要点.md", "法务核心-标准主服务协议模板.md"),
        expected_clauses=("服务水平",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-SLA弱化版.md",
        our_contract="""# 我方采购合同

## 服务水平
供应商应保证月度服务可用性不低于 99.9%，未达标时提供服务赔偿。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 服务水平
供应商将尽力维持服务稳定运行，但不对具体服务可用性作出承诺，也不提供服务赔偿。
""",
    ),
    LegalEvalCase(
        name="indemnity_removed",
        expected_decision="return",
        expected_risk="high",
        acceptable_titles=("法务核心-合同审查红线指引.md", "法务核心-标准主服务协议模板.md"),
        expected_clauses=("赔偿责任",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-赔偿删除版.md",
        our_contract="""# 我方采购合同

## 赔偿责任
供应商应就违约、侵权、数据处理不当造成的损失承担赔偿责任。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 赔偿责任
供应商不承担任何间接损失、第三方索赔或额外赔偿责任，仅退还已收服务费。
""",
    ),
    LegalEvalCase(
        name="advance_payment_watch",
        expected_decision="approve",
        expected_risk="medium",
        acceptable_titles=("法务核心-小额试点采购例外审批说明.md", "法务核心-分阶段付款与试运行安排说明.md", "法务核心-付款条款审查要点.md"),
        expected_clauses=("付款条款",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-预付款版.md",
        our_contract="""# 我方采购合同

## 付款条款
付款期限为验收后三十日，不设预付款。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 付款条款
签约后五个工作日内支付 20% 启动款，完成试运行并确认验收后支付剩余款项。
""",
        primary_titles=("法务核心-小额试点采购例外审批说明.md",),
        project_title="法务评测-内部试运行知识库工具",
        department="运营中台",
        category="software",
        budget_amount=48000,
        summary="采购内部试运行工具，仅供运营团队验证流程，不接触正式客户或生产业务数据。",
        business_value="在小范围内验证流程自动化能力。",
        data_scope="none",
    ),
    LegalEvalCase(
        name="audit_self_assessment_only",
        expected_decision="return",
        expected_risk="high",
        acceptable_titles=("法务核心-标准主服务协议模板.md", "法务核心-合同审查红线指引.md"),
        expected_clauses=("审计权",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-审计替代版.md",
        our_contract="""# 我方采购合同

## 审计权
如供应商处理我方业务数据，我方有权在合理通知后开展审计或要求提供审计证明。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 审计权
供应商仅提供年度自评报告，不接受客户现场审计或第三方审计。
""",
        primary_titles=("法务核心-标准主服务协议模板.md",),
    ),
    LegalEvalCase(
        name="overseas_law_watch",
        expected_decision="approve",
        expected_risk="medium",
        acceptable_titles=("法务核心-境外部署项目合同例外备忘录.md", "法务核心-国际业务合同变更处理说明.md", "法务核心-争议解决补充说明.md"),
        expected_clauses=("争议解决与适用法律",),
        our_contract_name="我方采购合同-标准版.md",
        counterparty_contract_name="对方回传合同-境外法律版.md",
        our_contract="""# 我方采购合同

## 争议解决
争议解决适用中华人民共和国法律，由我方所在地法院管辖。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 争议解决
本合同适用新加坡法律，争议提交新加坡国际仲裁中心仲裁。
""",
        primary_titles=("法务核心-境外部署项目合同例外备忘录.md",),
        project_title="法务评测-东南亚客服平台境外部署",
        department="国际业务部",
        category="customer-support-saas",
        budget_amount=860000,
        summary="面向海外子公司部署客服平台，由境外主体签约并在新加坡节点运行，需要结合当地监管与跨境访问安排。",
        business_value="支撑海外客服团队统一接入与运营。",
        data_scope="cross_border_customer_data",
    ),
    LegalEvalCase(
        name="pilot_self_assessment_watch",
        expected_decision="approve",
        expected_risk="medium",
        acceptable_titles=("法务核心-服务商自评材料接收说明.md", "法务核心-第三方安全证明材料适用说明.md", "法务核心-验证性项目供应商审查说明.md"),
        expected_clauses=("审计权",),
        our_contract_name="我方采购合同-试运行标准版.md",
        counterparty_contract_name="对方回传合同-试运行自评版.md",
        our_contract="""# 我方采购合同

## 审计权
如供应商处理我方核心业务数据，我方有权在合理通知后开展审计或要求提供审计证明。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 审计权
供应商优先提供 SOC 报告、渗透测试摘要和年度自评结论；若进入正式商用阶段，再由双方另行确认是否开展现场审计。
""",
        primary_titles=("法务核心-服务商自评材料接收说明.md",),
        project_title="法务评测-客服培训机器人试运行",
        department="培训运营部",
        category="software",
        budget_amount=42000,
        summary="本次仅采购内部试运行机器人工具，用于培训问答验证，不承载正式客户服务数据。",
        business_value="验证内部知识问答效果，决定是否进入正式采购。",
        data_scope="none",
    ),
    LegalEvalCase(
        name="migration_transition_watch",
        expected_decision="approve",
        expected_risk="medium",
        acceptable_titles=("法务核心-阶段性数据迁移控制说明.md", "法务核心-数据迁移项目特别说明.md", "法务核心-数据处理供应商检查清单.md"),
        expected_clauses=("数据处理", "安全事件通知"),
        our_contract_name="我方采购合同-迁移项目标准版.md",
        counterparty_contract_name="对方回传合同-迁移过渡版.md",
        our_contract="""# 我方采购合同

## 数据处理与安全
供应商仅可根据我方书面指示处理历史工单数据，未经同意不得跨境传输；如发生安全事件，应在二十四小时内通知我方。
""",
        counterparty_contract="""# 对方修改后的采购合同

## 数据处理与安全
为完成历史工单迁移，供应商可在迁移窗口内将数据中转至境外受控节点，迁移完成后三十日内删除临时副本；如发生安全事件，应在发现后尽快通知并同步处置进展。
""",
        primary_titles=("法务核心-阶段性数据迁移控制说明.md",),
        project_title="法务评测-历史工单归档迁移项目",
        department="客服运营部",
        category="migration-service",
        budget_amount=180000,
        summary="项目聚焦历史工单归档迁移，存在短期受控中转安排，但不用于长期持续运营。",
        business_value="完成旧系统下线前的数据迁移与归档。",
        data_scope="migration_data",
    ),
]

PROJECT_CONTEXT_BLOCKS = (
    "## 项目背景\n本项目用于采购客服与工单协同 SaaS，供应商将接触客户服务记录与工单附件。",
    "## 业务范围\n供应商负责部署客服工作台、知识库检索、工单流转与管理后台配置。",
    "## 交付边界\n本合同覆盖实施、培训、上线支持与后续运维服务，不含硬件采购。",
    "## 资料说明\n以下条款为双方当前谈判版本，仅用于法务红线审查，不代表最终签署版本。",
)

RECITAL_BLOCKS = (
    "## 鉴于条款\n鉴于甲方拟采购客户服务系统，乙方同意按本合同约定提供软件及实施服务。",
    "## 谈判背景\n双方已就采购范围、上线计划和数据处理边界完成初步沟通，现进入合同条款复核阶段。",
)

BENIGN_APPENDIX_BLOCKS = (
    "## 发票与结算\n双方按月对账，供应商应开具合法有效发票。",
    "## 项目联系人\n甲方联系人负责需求对接，乙方联系人负责实施与交付协调。",
    "## 上线安排\n双方应在约定时间窗口完成系统切换与培训支持。",
    "## 验收方式\n项目验收以双方确认的功能清单和上线记录为准。",
)

SCHEDULE_BLOCKS = (
    "## 附件一 服务清单\n乙方应按双方确认的实施计划完成部署、培训和试运行支持。",
    "## 附件二 项目排期\n双方应以书面排期表作为上线和验收的执行依据。",
)

NEGOTIATION_NOTE_BLOCKS = (
    "## 修订说明\n本版本为供应商回传的修订版，保留了付款、争议解决及责任条款的最新谈判表述。",
    "## 版本备注\n以下为本轮法务审查使用文本，部分表述沿用双方邮件往来中的修订版本。",
)

PARTY_REPLACEMENT_SETS = (
    (("我方", "甲方"), ("供应商", "乙方")),
    (("我方", "采购方"), ("供应商", "服务商")),
)

STYLE_REPLACEMENTS = (
    ("二十四小时", "24 小时"),
    ("过去十二个月已收取服务费总额", "近 12 个月已支付服务费总额"),
    ("发生安全事件后", "如发生安全事件"),
    ("未经书面许可不得向第三方披露", "未获书面许可不得向任何第三方披露"),
    ("根据我方书面指示处理数据", "按照我方书面指令处理数据"),
)

VARIANT_LABELS = (
    "base",
    "context",
    "party_shift",
    "appendix",
    "mixed_style",
    "numbered",
    "recital",
    "schedule",
    "formal",
    "negotiation",
)


def _apply_replacements(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    updated = text
    for source, target in replacements:
        updated = updated.replace(source, target)
    return updated


def _number_contract_sections(text: str) -> str:
    lines = text.splitlines()
    section_index = 0
    updated: list[str] = []
    for line in lines:
        if line.startswith("## "):
            section_index += 1
            updated.append(f"## 第{section_index}条 {line[3:].strip()}")
            continue
        updated.append(line)
    return "\n".join(updated)


def decorate_contract(text: str, *, variant_index: int, side: str) -> str:
    label = VARIANT_LABELS[variant_index] if variant_index < len(VARIANT_LABELS) else f"v{variant_index + 1}"
    body = text.strip()
    prefixes: list[str] = []
    suffixes: list[str] = []

    if label == "base":
        return body
    if label == "context":
        prefixes.append(PROJECT_CONTEXT_BLOCKS[variant_index % len(PROJECT_CONTEXT_BLOCKS)])
    elif label == "party_shift":
        body = _apply_replacements(body, PARTY_REPLACEMENT_SETS[0])
        if side == "counterparty":
            body = body.replace("对方修改后的采购合同", "乙方回传修订版协议")
    elif label == "appendix":
        suffixes.append(BENIGN_APPENDIX_BLOCKS[variant_index % len(BENIGN_APPENDIX_BLOCKS)])
    elif label == "mixed_style":
        prefixes.append(PROJECT_CONTEXT_BLOCKS[variant_index % len(PROJECT_CONTEXT_BLOCKS)])
        body = _apply_replacements(body, PARTY_REPLACEMENT_SETS[0])
        body = _apply_replacements(body, STYLE_REPLACEMENTS)
        if side == "counterparty":
            body = body.replace("对方修改后的采购合同", "供应商回传修订版协议")
        suffixes.append("## 版本说明\n本版本保留双方谈判过程中的修订痕迹，供法务核对。")
    elif label == "numbered":
        prefixes.append(PROJECT_CONTEXT_BLOCKS[variant_index % len(PROJECT_CONTEXT_BLOCKS)])
        body = _number_contract_sections(body)
    elif label == "recital":
        prefixes.append(RECITAL_BLOCKS[variant_index % len(RECITAL_BLOCKS)])
        body = _apply_replacements(body, PARTY_REPLACEMENT_SETS[1])
    elif label == "schedule":
        prefixes.append(PROJECT_CONTEXT_BLOCKS[variant_index % len(PROJECT_CONTEXT_BLOCKS)])
        suffixes.append(SCHEDULE_BLOCKS[variant_index % len(SCHEDULE_BLOCKS)])
        suffixes.append(BENIGN_APPENDIX_BLOCKS[variant_index % len(BENIGN_APPENDIX_BLOCKS)])
    elif label == "formal":
        prefixes.append(RECITAL_BLOCKS[variant_index % len(RECITAL_BLOCKS)])
        prefixes.append(PROJECT_CONTEXT_BLOCKS[variant_index % len(PROJECT_CONTEXT_BLOCKS)])
        body = _apply_replacements(body, PARTY_REPLACEMENT_SETS[1])
        body = _apply_replacements(body, STYLE_REPLACEMENTS)
        body = _number_contract_sections(body)
    elif label == "negotiation":
        prefixes.append(NEGOTIATION_NOTE_BLOCKS[variant_index % len(NEGOTIATION_NOTE_BLOCKS)])
        body = _apply_replacements(body, PARTY_REPLACEMENT_SETS[0])
        if side == "counterparty":
            body = body.replace("对方修改后的采购合同", "乙方红线回传版")
        suffixes.append(SCHEDULE_BLOCKS[variant_index % len(SCHEDULE_BLOCKS)])
        suffixes.append("## 邮件确认\n双方同意以本轮修订稿继续推进法务审查。")

    return "\n\n".join([*prefixes, body, *suffixes]).strip()


def expand_legal_eval_cases(base_cases: list[LegalEvalCase], variants_per_case: int = 5) -> list[LegalEvalCase]:
    expanded: list[LegalEvalCase] = []
    for case in base_cases:
        for variant_index in range(variants_per_case):
            label = VARIANT_LABELS[variant_index] if variant_index < len(VARIANT_LABELS) else f"v{variant_index + 1}"
            expanded.append(
                LegalEvalCase(
                    name=f"{case.name}_{label}",
                    expected_decision=case.expected_decision,
                    expected_risk=case.expected_risk,
                    acceptable_titles=case.acceptable_titles,
                    expected_clauses=case.expected_clauses,
                    our_contract_name=case.our_contract_name.replace(".md", f"-{label}.md"),
                    counterparty_contract_name=case.counterparty_contract_name.replace(".md", f"-{label}.md"),
                    our_contract=decorate_contract(case.our_contract, variant_index=variant_index, side="our"),
                    counterparty_contract=decorate_contract(
                        case.counterparty_contract,
                        variant_index=variant_index,
                        side="counterparty",
                    ),
                    primary_titles=case.primary_titles,
                    project_title=case.project_title,
                    department=case.department,
                    category=case.category,
                    budget_amount=case.budget_amount,
                    summary=case.summary,
                    business_value=case.business_value,
                    data_scope=case.data_scope,
                )
            )
    return expanded


LEGAL_BENCHMARK_CASES = expand_legal_eval_cases(LEGAL_EVAL_CASES, variants_per_case=10)


def login_headers(client: TestClient, username: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"username": username, "password": username})
    response.raise_for_status()
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def create_runtime_dir() -> Path:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    runtime_dir = RUNTIME_ROOT / f"run_{os.getpid()}"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def create_runtime_client(runtime_dir: Path) -> TestClient:
    embedding_model = str(EMBEDDING_MODEL_PATH) if EMBEDDING_MODEL_PATH.exists() else ""
    reranker_model = str(RERANKER_MODEL_PATH) if RERANKER_MODEL_PATH.exists() else "BAAI/bge-reranker-base"
    settings = build_settings(
        database_url=f"sqlite:///{(runtime_dir / 'legal_eval.db').resolve().as_posix()}",
        storage_dir=str((runtime_dir / "uploads").resolve()),
        api_base_url="http://testserver",
        embedding_model=embedding_model,
        reranker_model=reranker_model,
        reranker_enabled=True,
    )
    app = create_app(settings)
    return TestClient(app)


def upload_knowledge_base(client: TestClient, admin_headers: dict[str, str]) -> None:
    print(f"[legal-eval] upload kb docs={len(LEGAL_KB_FILES)}")
    for index, (name, content) in enumerate(LEGAL_KB_FILES, start=1):
        response = client.post(
            "/knowledge/upload",
            headers=admin_headers,
            files={"file": (name, content.encode("utf-8"), "text/markdown")},
            data={"allowed_roles": "employee", "tags": "baseline,legal"},
        )
        response.raise_for_status()
        task_id = response.json()["task_id"]
        task = client.get(f"/knowledge/tasks/{task_id}", headers=admin_headers)
        task.raise_for_status()
        print(f"[legal-eval] kb progress={index}/{len(LEGAL_KB_FILES)} status={task.json()['status']} title={name}")


def create_project(client: TestClient, business_headers: dict[str, str], *, case: LegalEvalCase) -> dict[str, object]:
    payload = {
        "title": case.project_title,
        "requester_name": "王悦",
        "department": case.department,
        "vendor_name": "云服科技",
        "category": case.category,
        "budget_amount": case.budget_amount,
        "currency": "CNY",
        "summary": case.summary,
        "business_value": case.business_value,
        "target_go_live_date": "2026-06-30",
        "data_scope": case.data_scope,
    }
    response = client.post("/projects", headers=business_headers, json=payload)
    response.raise_for_status()
    return response.json()


def get_project(client: TestClient, headers: dict[str, str], project_id: str) -> dict[str, object]:
    response = client.get(f"/projects/{project_id}", headers=headers)
    response.raise_for_status()
    return response.json()


def complete_stage(client: TestClient, headers: dict[str, str], project: dict[str, object]) -> dict[str, object]:
    project_id = str(project["id"])
    current_stage = str(project["current_stage"])
    for task in project["tasks"]:
        if task["stage"] != current_stage or task["status"] == "done":
            continue
        response = client.patch(
            f"/projects/{project_id}/tasks/{task['id']}",
            headers=headers,
            json={"status": "done"},
        )
        response.raise_for_status()
    for artifact in project["artifacts"]:
        if artifact["stage"] != current_stage or artifact["status"] in {"provided", "approved"}:
            continue
        response = client.patch(
            f"/projects/{project_id}/artifacts/{artifact['id']}",
            headers=headers,
            json={"status": "provided"},
        )
        response.raise_for_status()
    return get_project(client, headers, project_id)


def reach_legal_stage(
    client: TestClient,
    *,
    business_headers: dict[str, str],
    manager_headers: dict[str, str],
    procurement_headers: dict[str, str],
    case: LegalEvalCase,
) -> dict[str, object]:
    project = create_project(client, business_headers, case=case)
    project_id = str(project["id"])
    submit_response = client.post(f"/projects/{project_id}/submit", headers=business_headers, json={"reason": ""})
    submit_response.raise_for_status()
    approve_response = client.post(
        f"/projects/{project_id}/manager-decision",
        headers=manager_headers,
        json={"decision": "approve", "reason": "进入采购阶段"},
    )
    approve_response.raise_for_status()
    project = approve_response.json()
    project = complete_stage(client, procurement_headers, project)
    vendor_id = str(project["vendors"][0]["id"])
    select_response = client.post(
        f"/projects/{project_id}/vendors/{vendor_id}/select",
        headers=procurement_headers,
        json={"reason": "进入法务合同审查"},
    )
    select_response.raise_for_status()
    return select_response.json()


def upload_legal_contracts(
    client: TestClient,
    *,
    legal_headers: dict[str, str],
    project: dict[str, object],
    case: LegalEvalCase,
) -> dict[str, object]:
    project_id = str(project["id"])
    legal_artifacts = [artifact for artifact in project["artifacts"] if artifact["stage"] == "legal_review"]
    our_contract = next(artifact for artifact in legal_artifacts if artifact["artifact_type"] == "our_procurement_contract")
    counterparty_contract = next(
        artifact for artifact in legal_artifacts if artifact["artifact_type"] == "counterparty_redline_contract"
    )
    upload_pairs = (
        (our_contract, case.our_contract_name, case.our_contract),
        (counterparty_contract, case.counterparty_contract_name, case.counterparty_contract),
    )
    for artifact, filename, content in upload_pairs:
        response = client.post(
            f"/projects/{project_id}/artifacts/{artifact['id']}/upload",
            headers=legal_headers,
            files={"file": (filename, content.encode("utf-8"), "text/markdown")},
        )
        response.raise_for_status()

    refreshed = get_project(client, legal_headers, project_id)
    for artifact in refreshed["artifacts"]:
        if artifact["stage"] != "legal_review" or artifact["status"] in {"provided", "approved"}:
            continue
        response = client.patch(
            f"/projects/{project_id}/artifacts/{artifact['id']}",
            headers=legal_headers,
            json={"status": "provided"},
        )
        response.raise_for_status()
    return get_project(client, legal_headers, project_id)


def _retrieve_for_strategy(retrieval_service, *, strategy: str, db, query: str, user_role: str, top_k: int, plan=None):
    variants = retrieval_service.build_query_variants(query, plan)
    task_mode = str((plan or {}).get("task_mode", "knowledge_qa"))
    source_type_hints = [str(item) for item in (plan or {}).get("source_type_hints", [])]
    document_hints = [str(item) for item in (plan or {}).get("document_hints", [])]
    accessible_chunks = retrieval_service._load_accessible_chunks(db, user_role=user_role)
    accessible_chunks = retrieval_service._filter_accessible_chunks_for_task(
        accessible_chunks,
        task_mode=task_mode,
        document_hints=document_hints,
    )
    rerank_k = int((plan or {}).get("rerank_k", max(top_k * 3, 10)))
    candidate_limit = max(min(rerank_k, top_k * 4), top_k + 4, 8)

    bm25_candidates = retrieval_service._bm25_retrieve(
        variants=variants,
        records=accessible_chunks,
        candidate_limit=candidate_limit,
        source_type_hints=source_type_hints,
        document_hints=document_hints,
    )
    semantic_candidates = retrieval_service._semantic_retrieve(
        db,
        variants=variants,
        user_role=user_role,
        candidate_limit=candidate_limit,
        source_type_hints=source_type_hints,
        document_hints=document_hints,
        accessible_chunks=accessible_chunks,
    )
    merged = retrieval_service._merge_candidates_rrf(bm25_candidates, semantic_candidates)

    if strategy == "bm25_only":
        selected = _select_top_chunks(bm25_candidates, top_k=top_k)
        rerank_debug = {"rerank_strategy": "disabled", "cross_encoder_active": False}
    elif strategy == "semantic_only":
        selected = _select_top_chunks(semantic_candidates, top_k=top_k)
        rerank_debug = {"rerank_strategy": "disabled", "cross_encoder_active": False}
    elif strategy == "hybrid_rrf":
        selected = retrieval_service._select_legal_rrf_chunks(
            merged,
            bm25_candidates=bm25_candidates,
            query_variants=variants,
            top_k=top_k,
        )
        rerank_debug = {"rerank_strategy": "legal_rrf_shortlist", "cross_encoder_active": False}
    elif strategy == "hybrid_rrf_rerank":
        return retrieval_service.retrieve(
            db,
            query=query,
            user_role=user_role,
            top_k=top_k,
            plan=plan,
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    return selected, {
        "original_query": query,
        "rewritten_query": variants[1] if len(variants) > 1 else query,
        "query_variants": variants,
        "document_hints": document_hints,
        "domain_labels": list((plan or {}).get("domain_labels", [])),
        "bm25_candidate_count": len(bm25_candidates),
        "semantic_candidate_count": len(semantic_candidates),
        "rrf_merged_candidate_count": len(merged),
        "keyword_candidate_count": len(bm25_candidates),
        "vector_candidate_count": len(semantic_candidates),
        "merged_candidate_count": len(merged),
        **rerank_debug,
    }


@contextmanager
def override_retrieve(container, strategy: str):
    if strategy == "hybrid_rrf_rerank":
        yield
        return

    retrieval_service = container.retrieval_service
    original_retrieve = retrieval_service.retrieve

    def _patched(self, db, *, query: str, user_role: str, top_k: int, plan=None):
        return _retrieve_for_strategy(
            self,
            strategy=strategy,
            db=db,
            query=query,
            user_role=user_role,
            top_k=top_k,
            plan=plan,
        )

    retrieval_service.retrieve = MethodType(_patched, retrieval_service)
    try:
        yield
    finally:
        retrieval_service.retrieve = original_retrieve


def _doc_rank_metrics(returned_titles: list[str], acceptable_titles: tuple[str, ...]) -> tuple[float, float, float]:
    acceptable = set(acceptable_titles)
    hit1 = 1.0 if returned_titles[:1] and returned_titles[0] in acceptable else 0.0
    hit3 = 1.0 if any(title in acceptable for title in returned_titles[:3]) else 0.0
    mrr = 0.0
    for index, title in enumerate(returned_titles, start=1):
        if title in acceptable:
            mrr = 1.0 / index
            break
    return hit1, hit3, mrr


def _clause_recall(found_items: list[str], expected_clauses: tuple[str, ...]) -> float:
    if not expected_clauses:
        return 1.0
    joined = " ".join(found_items)
    matched = sum(1 for clause in expected_clauses if clause in joined)
    return matched / len(expected_clauses)


def _filter_kb_titles(citations: list[dict[str, object]]) -> list[str]:
    titles: list[str] = []
    for item in citations:
        title = str(item.get("document_title", "")).strip()
        if title.startswith(LEGAL_DOC_PREFIX) and title not in titles:
            titles.append(title)
    return titles


def _selected_kb_titles(review: dict[str, object]) -> list[str]:
    debug_summary = review.get("debug_summary", {}) or {}
    retrieval_debug = debug_summary.get("retrieval", {}) if isinstance(debug_summary, dict) else {}
    selected_titles = retrieval_debug.get("selected_titles", []) if isinstance(retrieval_debug, dict) else []
    titles = [
        str(title).strip()
        for title in selected_titles
        if str(title).strip().startswith(LEGAL_DOC_PREFIX)
    ]
    if titles:
        return list(dict.fromkeys(titles))
    return _filter_kb_titles(review.get("citations", []))


def _primary_titles(case: LegalEvalCase) -> tuple[str, ...]:
    if case.primary_titles:
        return case.primary_titles
    if case.acceptable_titles:
        return (case.acceptable_titles[0],)
    return ()


def run_case(client: TestClient, headers: dict[str, dict[str, str]], *, case: LegalEvalCase) -> dict[str, object]:
    project = reach_legal_stage(
        client,
        business_headers=headers["business"],
        manager_headers=headers["manager"],
        procurement_headers=headers["procurement"],
        case=case,
    )
    project = upload_legal_contracts(
        client,
        legal_headers=headers["legal"],
        project=project,
        case=case,
    )
    project_id = str(project["id"])
    response = client.post(
        f"/projects/{project_id}/legal/review",
        headers=headers["legal"],
        json={"top_k": 4},
    )
    response.raise_for_status()
    payload = response.json()
    assessment = payload["assessment"]
    review = payload["review"]
    kb_titles = _selected_kb_titles(review)
    clause_items = list(assessment.get("clause_gaps", [])) + list(assessment.get("risk_flags", []))
    hit1, hit3, mrr = _doc_rank_metrics(kb_titles, case.acceptable_titles)
    primary_hit1, primary_hit3, primary_mrr = _doc_rank_metrics(kb_titles, _primary_titles(case))
    clause_recall = _clause_recall(clause_items, case.expected_clauses)
    decision_correct = 1.0 if assessment["decision_suggestion"] == case.expected_decision else 0.0
    risk_correct = 1.0 if assessment["risk_level"] == case.expected_risk else 0.0
    end_to_end_success = 1.0 if decision_correct and risk_correct and hit3 else 0.0
    return {
        "case": case.name,
        "expected_decision": case.expected_decision,
        "actual_decision": assessment["decision_suggestion"],
        "expected_risk": case.expected_risk,
        "actual_risk": assessment["risk_level"],
        "kb_titles": kb_titles,
        "acceptable_titles": list(case.acceptable_titles),
        "primary_titles": list(_primary_titles(case)),
        "clause_recall": clause_recall,
        "doc_hit@1": hit1,
        "doc_hit@3": hit3,
        "doc_mrr": mrr,
        "primary_doc_hit@1": primary_hit1,
        "primary_doc_hit@3": primary_hit3,
        "primary_doc_mrr": primary_mrr,
        "decision_correct": decision_correct,
        "risk_correct": risk_correct,
        "success": end_to_end_success,
        "summary": assessment.get("summary", ""),
        "clause_gaps": list(assessment.get("clause_gaps", [])),
        "risk_flags": list(assessment.get("risk_flags", [])),
        "retrieval_debug": dict(review.get("debug_summary", {}).get("retrieval", {})),
    }


def evaluate_pipeline(client: TestClient, headers: dict[str, dict[str, str]], *, strategy: str, cases: list[LegalEvalCase]) -> dict[str, object]:
    container = client.app.state.container
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    print(f"[legal-eval] start pipeline={strategy} cases={len(cases)}")
    with override_retrieve(container, strategy):
        for index, case in enumerate(cases, start=1):
            result = run_case(client, headers, case=case)
            results.append(result)
            if not result["success"]:
                failures.append(
                    {
                        "case": case.name,
                        "expected_decision": case.expected_decision,
                        "actual_decision": result["actual_decision"],
                        "expected_risk": case.expected_risk,
                        "actual_risk": result["actual_risk"],
                        "acceptable_titles": list(case.acceptable_titles),
                        "primary_titles": list(_primary_titles(case)),
                        "returned_titles": result["kb_titles"],
                    }
                )
            print(
                f"[legal-eval] pipeline={strategy} progress={index}/{len(cases)} "
                f"case={case.name} success={int(result['success'])} kb_hit3={result['doc_hit@3']:.0f}"
            )

    elapsed = round(time.perf_counter() - started, 2)
    case_count = max(len(results), 1)
    first_retrieval_debug = results[0]["retrieval_debug"] if results else {}
    return {
        "success": round(sum(item["success"] for item in results) / case_count, 4),
        "decision_accuracy": round(sum(item["decision_correct"] for item in results) / case_count, 4),
        "risk_accuracy": round(sum(item["risk_correct"] for item in results) / case_count, 4),
        "clause_recall": round(sum(item["clause_recall"] for item in results) / case_count, 4),
        "doc_hit@1": round(sum(item["doc_hit@1"] for item in results) / case_count, 4),
        "doc_hit@3": round(sum(item["doc_hit@3"] for item in results) / case_count, 4),
        "doc_mrr": round(sum(item["doc_mrr"] for item in results) / case_count, 4),
        "primary_doc_hit@1": round(sum(item["primary_doc_hit@1"] for item in results) / case_count, 4),
        "primary_doc_hit@3": round(sum(item["primary_doc_hit@3"] for item in results) / case_count, 4),
        "primary_doc_mrr": round(sum(item["primary_doc_mrr"] for item in results) / case_count, 4),
        "cross_encoder_active": bool(first_retrieval_debug.get("cross_encoder_active", False)),
        "elapsed_seconds": elapsed,
        "failures": failures[:8],
        "cases": results,
    }


def main() -> None:
    benchmark_cases = LEGAL_BENCHMARK_CASES
    runtime_dir = create_runtime_dir()
    with create_runtime_client(runtime_dir) as client:
        headers = {
            "admin": login_headers(client, "admin"),
            "business": login_headers(client, "business"),
            "manager": login_headers(client, "manager"),
            "procurement": login_headers(client, "procurement"),
            "legal": login_headers(client, "legal"),
        }
        upload_knowledge_base(client, headers["admin"])
        pipelines = {
            name: evaluate_pipeline(client, headers, strategy=name, cases=benchmark_cases)
            for name in DEFAULT_PIPELINES
        }
        container = client.app.state.container
        embedding_backend = "sentence_transformer" if container.embedding_service.using_sentence_transformer else "hash_fallback"
        embedding_dim = container.embedding_service.dimensions

    result = {
        "case_count": len(benchmark_cases),
        "base_case_count": len(LEGAL_EVAL_CASES),
        "variants_per_base_case": len(LEGAL_BENCHMARK_CASES) // max(len(LEGAL_EVAL_CASES), 1),
        "kb_doc_count": len(LEGAL_KB_FILES),
        "embedding_model": str(EMBEDDING_MODEL_PATH if EMBEDDING_MODEL_PATH.exists() else ""),
        "embedding_backend": embedding_backend,
        "embedding_dimension": embedding_dim,
        "pipelines": pipelines,
    }
    result_path = runtime_dir / "legal_ablation_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "case_count": result["case_count"],
        "base_case_count": result["base_case_count"],
        "variants_per_base_case": result["variants_per_base_case"],
        "kb_doc_count": result["kb_doc_count"],
        "embedding_backend": embedding_backend,
        "embedding_dimension": embedding_dim,
        "result_file": str(result_path.resolve()),
        "pipelines": {
            name: {
                key: pipeline[key]
                for key in (
                    "success",
                    "decision_accuracy",
                    "risk_accuracy",
                    "clause_recall",
                    "doc_hit@1",
                    "doc_hit@3",
                    "doc_mrr",
                    "primary_doc_hit@1",
                    "primary_doc_hit@3",
                    "primary_doc_mrr",
                    "cross_encoder_active",
                    "elapsed_seconds",
                )
            }
            for name, pipeline in pipelines.items()
        },
    }
    summary_path = runtime_dir / "legal_ablation_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[legal-eval] compact summary")
    print(f"  result_file: {result_path.resolve()}")
    print(f"  summary_file: {summary_path.resolve()}")
    print(
        f"  cases={result['case_count']} base_cases={result['base_case_count']} "
        f"variants={result['variants_per_base_case']} docs={result['kb_doc_count']} "
        f"embedding={embedding_backend}({embedding_dim})"
    )
    for name, pipeline in pipelines.items():
        print(
            f"  {name}: success={pipeline['success']} decision_acc={pipeline['decision_accuracy']} "
            f"risk_acc={pipeline['risk_accuracy']} clause_recall={pipeline['clause_recall']} "
            f"doc_hit@1={pipeline['doc_hit@1']} doc_hit@3={pipeline['doc_hit@3']} "
            f"doc_mrr={pipeline['doc_mrr']} primary_hit@1={pipeline['primary_doc_hit@1']} "
            f"primary_hit@3={pipeline['primary_doc_hit@3']} primary_mrr={pipeline['primary_doc_mrr']} "
            f"cross_encoder={pipeline['cross_encoder_active']} "
            f"elapsed={pipeline['elapsed_seconds']}s"
        )


if __name__ == "__main__":
    main()
