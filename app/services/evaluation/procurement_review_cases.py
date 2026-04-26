from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcurementReviewProjectInput:
    title: str
    department: str
    category: str
    budget_amount: float
    summary: str
    business_value: str
    data_scope: str = "none"
    currency: str = "CNY"


@dataclass(frozen=True)
class ProcurementReviewVendorInput:
    vendor_name: str
    source_platform: str
    source_url: str
    contact_email: str
    profile_summary: str
    procurement_notes: str
    handles_company_data: bool
    requires_system_integration: bool
    quoted_amount: float
    contact_name: str = ""
    contact_phone: str = ""
    focus_points: str = ""


@dataclass(frozen=True)
class ProcurementReviewExpected:
    required_analysis_tags: tuple[str, ...]
    forbidden_analysis_tags: tuple[str, ...]
    required_missing_materials: tuple[str, ...]
    forbidden_missing_materials: tuple[str, ...]
    acceptable_titles: tuple[str, ...]


@dataclass(frozen=True)
class ProcurementReviewEvalCase:
    case_id: str
    scenario_type: str
    description: str
    project: ProcurementReviewProjectInput
    vendor: ProcurementReviewVendorInput
    expected: ProcurementReviewExpected


TITLE_ONBOARDING = "采购核心-供应商准入办法.md"
TITLE_APPROVAL = "采购核心-采购审批矩阵.md"
TITLE_SECURITY = "采购核心-安全评审操作流程.md"
TITLE_FAQ = "采购核心-常见问答.csv"
TITLE_BACKGROUND = "采购核心-供应商背景核验清单.md"
TITLE_SMALL_SAAS = "采购核心-小额SaaS快速引入指引.md"
TITLE_INTEGRATION = "采购核心-系统接入类采购补充要求.md"
TITLE_BUDGET = "采购核心-预算例外处理说明.md"
TITLE_DATA = "采购核心-第三方数据处理补充说明.md"
TITLE_SERVICE = "采购核心-外包与服务类供应商筛选要点.md"
TITLE_ESCALATION = "采购核心-采购升级判断案例集.md"


NON_RISK_TAGS = (
    "material_gate_failed",
    "subject_identity_gap",
    "source_reliability_risk",
    "service_capability_gap",
    "business_fit_gap",
    "budget_or_fit_blocker",
    "manual_replacement_recommended",
    "budget_overrun",
    "data_handling_risk",
    "system_integration_risk",
    "missing_security_materials",
    "missing_data_processing_materials",
    "missing_hosting_details",
    "missing_incident_commitment",
)

COMMON_FORBIDDEN_MISSING = (
    "供应商主体信息",
    "产品/服务说明",
    "可追溯公开来源",
    "采购用途/商务背景",
    "供应商联系邮箱",
    "报价或预计合作金额",
    "安全问卷或安全白皮书",
    "数据处理说明或隐私/DPA材料",
    "数据存储/部署/数据流说明",
    "安全事件通知承诺",
)

CASE_BLUEPRINTS = (
    ("客户服务部", "智能客服机器人", "自动回复、工单分流和服务质检", "降低一线重复答复比例并稳定服务口径"),
    ("财务共享中心", "发票识别与报销校验工具", "发票 OCR、报销单据校验和异常提示", "减少人工录票和发票合规初筛时间"),
    ("人力资源部", "排班与考勤优化系统", "门店排班、调班审批和异常考勤提醒", "提升排班公平性并减少月末核对工作量"),
    ("信息安全部", "终端资产盘点平台", "电脑资产发现、补丁状态统计和风险设备定位", "提高资产台账准确率并缩短排查周期"),
    ("市场运营部", "活动报名与线索收集平台", "报名表单、线索分层和活动数据回收", "提升活动转化数据的完整性"),
    ("销售支持部", "销售预测辅助工具", "商机阶段预测、跟进提醒和回款概率分析", "辅助团队识别重点跟进客户"),
    ("培训发展部", "在线学习平台", "课程发布、考试测评和学习进度追踪", "统一员工培训记录并提高课程完成率"),
    ("行政管理部", "会议室预约系统", "会议室占用、访客登记和设备报修联动", "减少会议资源冲突和线下沟通成本"),
    ("仓储物流部", "库存预警与补货系统", "库存水位、滞销预警和补货建议", "降低缺货风险并提升周转可视化"),
    ("采购管理部", "供应商绩效看板", "交付准时率、质量问题和价格波动统计", "提升供应商复盘效率"),
    ("法务协同部", "合同台账检索工具", "合同元数据检索、到期提醒和版本定位", "减少合同查找时间并支持续签提醒"),
    ("客服质检部", "通话质检抽样工具", "录音抽样、敏感词提示和质检评分", "提升抽检覆盖率和问题发现效率"),
    ("品牌公关部", "舆情监测平台", "媒体声量、负面预警和竞品话题跟踪", "缩短舆情发现到响应的时间"),
    ("门店运营部", "巡店问题整改系统", "巡店拍照、问题派单和整改闭环", "提高门店执行问题的闭环率"),
    ("研发效能部", "缺陷趋势分析工具", "缺陷归因、版本趋势和处理时长统计", "辅助研发团队识别质量薄弱环节"),
    ("数据分析部", "指标看板自助搭建工具", "经营指标配置、权限分级和图表发布", "让业务团队减少临时报表需求"),
    ("客户成功部", "续费健康度评分系统", "客户使用频率、满意度和续费风险评分", "提前识别高风险客户并安排跟进"),
    ("售后服务部", "备件维修派单系统", "备件库存、维修派单和服务时效统计", "减少售后响应延迟"),
    ("生产计划部", "产能排程辅助系统", "产线负荷、订单优先级和排程冲突提示", "提高排产稳定性并降低临时插单影响"),
    ("合规管理部", "制度宣贯确认平台", "制度阅读确认、抽测题库和留痕统计", "提升制度触达和员工确认留痕"),
    ("运营管理部", "门店客流分析工具", "客流趋势、热区统计和高峰提醒", "支持门店人员安排和促销复盘"),
    ("质量管理部", "供应商来料异常跟踪系统", "来料异常登记、责任归因和整改追踪", "提升质量异常闭环透明度"),
    ("渠道管理部", "经销商资料审核平台", "资质材料收集、到期提醒和审核流转", "减少渠道准入资料反复沟通"),
    ("产品运营部", "用户反馈聚类工具", "反馈标签、需求聚类和版本建议汇总", "帮助产品团队识别高频问题"),
    ("审计监察部", "费用异常抽检工具", "费用规则校验、异常样本抽取和复核记录", "提升费用抽检效率"),
)

VENDOR_PREFIXES = ("星云", "蓝图", "远帆", "明点", "智策", "衡石", "鹿鸣", "北辰", "云阶", "棱镜")


def _vendor_name(product: str, index: int) -> str:
    short_product = (
        product.replace("系统", "")
        .replace("平台", "")
        .replace("工具", "")
        .replace("机器人", "")
    )
    return f"{VENDOR_PREFIXES[index % len(VENDOR_PREFIXES)]}{short_product}{index + 1:02d}"


def _project(
    *,
    blueprint: tuple[str, str, str, str],
    budget_amount: float,
    data_scope: str = "none",
) -> ProcurementReviewProjectInput:
    department, product, scenario, business_value = blueprint
    return ProcurementReviewProjectInput(
        title=f"{department}{product}采购项目",
        department=department,
        category="software",
        budget_amount=budget_amount,
        summary=f"{department}计划引入{product}，重点覆盖{scenario}，需要采购判断候选供应商是否值得继续推进。",
        business_value=business_value,
        data_scope=data_scope,
    )


def _vendor(
    *,
    vendor_name: str,
    source_platform: str,
    source_url: str,
    contact_email: str,
    profile_summary: str,
    procurement_notes: str,
    handles_company_data: bool,
    requires_system_integration: bool,
    quoted_amount: float,
    focus_points: str = "",
) -> ProcurementReviewVendorInput:
    return ProcurementReviewVendorInput(
        vendor_name=vendor_name,
        source_platform=source_platform,
        source_url=source_url,
        contact_email=contact_email,
        profile_summary=profile_summary,
        procurement_notes=procurement_notes,
        handles_company_data=handles_company_data,
        requires_system_integration=requires_system_integration,
        quoted_amount=quoted_amount,
        focus_points=focus_points,
    )


def _expected(
    *,
    required_analysis_tags: tuple[str, ...],
    forbidden_analysis_tags: tuple[str, ...],
    required_missing_materials: tuple[str, ...],
    forbidden_missing_materials: tuple[str, ...],
    acceptable_titles: tuple[str, ...],
) -> ProcurementReviewExpected:
    return ProcurementReviewExpected(
        required_analysis_tags=required_analysis_tags,
        forbidden_analysis_tags=forbidden_analysis_tags,
        required_missing_materials=required_missing_materials,
        forbidden_missing_materials=forbidden_missing_materials,
        acceptable_titles=acceptable_titles,
    )


def _clean_cases() -> list[ProcurementReviewEvalCase]:
    cases: list[ProcurementReviewEvalCase] = []
    for index, blueprint in enumerate(CASE_BLUEPRINTS[:20]):
        _department, product, scenario, _value = blueprint
        budget = 150000 + index * 13000
        vendor_name = _vendor_name(product, index)
        cases.append(
            ProcurementReviewEvalCase(
                case_id=f"clean_{index:02d}",
                scenario_type="analysis_clean",
                description=f"{product}资料完整且低风险",
                project=_project(blueprint=blueprint, budget_amount=budget),
                vendor=_vendor(
                    vendor_name=vendor_name,
                    source_platform="官网",
                    source_url=f"https://vendor{index:02d}.example.com",
                    contact_email=f"bd{index:02d}@vendor.example.com",
                    profile_summary=f"{vendor_name}提供{product}，覆盖{scenario}，支持权限配置、使用报表和基础实施服务。",
                    procurement_notes="业务已完成产品演示和试用反馈，当前只需要采购按准入制度做风险提示，不要求系统替代人工拍板。",
                    handles_company_data=False,
                    requires_system_integration=False,
                    quoted_amount=round(budget * 0.72, 2),
                ),
                expected=_expected(
                    required_analysis_tags=(),
                    forbidden_analysis_tags=NON_RISK_TAGS,
                    required_missing_materials=(),
                    forbidden_missing_materials=COMMON_FORBIDDEN_MISSING,
                    acceptable_titles=(TITLE_ONBOARDING, TITLE_BACKGROUND, TITLE_FAQ, TITLE_SMALL_SAAS),
                ),
            )
        )
    return cases


def _budget_attention_cases() -> list[ProcurementReviewEvalCase]:
    cases: list[ProcurementReviewEvalCase] = []
    for offset, blueprint in enumerate(CASE_BLUEPRINTS[:20]):
        index = offset + 20
        _department, product, scenario, _value = blueprint
        budget = 180000 + offset * 17000
        generic_summary = offset % 3 == 1
        required_tags = ("budget_overrun",) + (("business_fit_gap",) if generic_summary else ())
        profile_summary = (
            "供应商介绍更偏通用低代码表单、任务流和审批编排，没有说明和本次专业场景的一一对应能力。"
            if generic_summary
            else f"供应商提供{product}能力，覆盖{scenario}，但商务报价明显高于当前项目预算。"
        )
        cases.append(
            ProcurementReviewEvalCase(
                case_id=f"budget_{offset:02d}",
                scenario_type="analysis_budget_attention",
                description=f"{product}预算或商务可行性关注",
                project=_project(blueprint=blueprint, budget_amount=budget),
                vendor=_vendor(
                    vendor_name=_vendor_name(product, index),
                    source_platform="官网",
                    source_url=f"https://pricing{offset:02d}.example.com",
                    contact_email=f"price{offset:02d}@vendor.example.com",
                    profile_summary=profile_summary,
                    procurement_notes="业务认可供应商演示效果，但报价已经超过预算，需要采购提示预算例外或重新议价风险。",
                    handles_company_data=False,
                    requires_system_integration=False,
                    quoted_amount=round(budget * (1.08 + (offset % 4) * 0.04), 2),
                    focus_points="重点关注预算匹配、是否需要走预算例外，以及能力描述是否真的贴合本次采购。",
                ),
                expected=_expected(
                    required_analysis_tags=required_tags,
                    forbidden_analysis_tags=("material_gate_failed", "source_reliability_risk", "subject_identity_gap"),
                    required_missing_materials=(),
                    forbidden_missing_materials=COMMON_FORBIDDEN_MISSING,
                    acceptable_titles=(TITLE_APPROVAL, TITLE_BUDGET, TITLE_ONBOARDING, TITLE_FAQ),
                ),
            )
        )
    return cases


def _data_review_cases() -> list[ProcurementReviewEvalCase]:
    cases: list[ProcurementReviewEvalCase] = []
    patterns = (
        (False, False, False, False),
        (True, False, False, False),
        (False, True, False, False),
        (False, False, True, False),
        (False, False, False, True),
    )
    for offset, blueprint in enumerate(CASE_BLUEPRINTS[:25]):
        index = offset + 40
        _department, product, scenario, _value = blueprint
        budget = 240000 + offset * 9000
        has_security, has_privacy, has_hosting, has_incident = patterns[offset % len(patterns)]
        notes = [f"业务预计让供应商处理客户、员工或经营数据，并接入内部流程支撑{scenario}。"]
        required_missing: list[str] = []
        if has_security:
            notes.append("供应商已提供安全白皮书和基础安全问卷。")
        else:
            required_missing.append("安全问卷或安全白皮书")
        if has_privacy:
            notes.append("供应商已提供隐私政策和数据处理说明。")
        else:
            required_missing.append("数据处理说明或隐私/DPA材料")
        if has_hosting:
            notes.append("供应商说明数据部署区域、备份位置和主要数据流。")
        else:
            required_missing.append("数据存储/部署/数据流说明")
        if has_incident:
            notes.append("供应商承诺安全事件通知和升级联系人。")
        else:
            required_missing.append("安全事件通知承诺")
        required_tags = tuple(
            tag
            for tag in (
                "data_handling_risk",
                "system_integration_risk",
                None if has_security else "missing_security_materials",
                None if has_privacy else "missing_data_processing_materials",
                None if has_hosting else "missing_hosting_details",
                None if has_incident else "missing_incident_commitment",
            )
            if tag is not None
        )
        cases.append(
            ProcurementReviewEvalCase(
                case_id=f"data_{offset:02d}",
                scenario_type="analysis_data_review",
                description=f"{product}涉及数据处理或系统接入",
                project=_project(blueprint=blueprint, budget_amount=budget, data_scope="customer_data"),
                vendor=_vendor(
                    vendor_name=_vendor_name(product, index),
                    source_platform="官网",
                    source_url=f"https://secure{offset:02d}.example.com",
                    contact_email=f"security{offset:02d}@vendor.example.com",
                    profile_summary=f"供应商提供{product}，可覆盖{scenario}，支持账号权限、API 接入和使用数据统计。",
                    procurement_notes=" ".join(notes),
                    handles_company_data=True,
                    requires_system_integration=True,
                    quoted_amount=round(budget * 0.91, 2),
                    focus_points="重点关注数据边界、系统接入权限、部署位置和安全事件响应承诺。",
                ),
                expected=_expected(
                    required_analysis_tags=required_tags,
                    forbidden_analysis_tags=("material_gate_failed", "source_reliability_risk", "subject_identity_gap"),
                    required_missing_materials=tuple(required_missing),
                    forbidden_missing_materials=("供应商主体信息", "产品/服务说明", "可追溯公开来源", "采购用途/商务背景", "供应商联系邮箱", "报价或预计合作金额"),
                    acceptable_titles=(TITLE_SECURITY, TITLE_DATA, TITLE_INTEGRATION, TITLE_APPROVAL, TITLE_ESCALATION),
                ),
            )
        )
    return cases


def _source_identity_cases() -> list[ProcurementReviewEvalCase]:
    cases: list[ProcurementReviewEvalCase] = []
    for offset, blueprint in enumerate(CASE_BLUEPRINTS[:20]):
        index = offset + 70
        _department, product, _scenario, _value = blueprint
        social_source = offset % 2 == 0
        placeholder_vendor = offset % 4 in {1, 3}
        vendor_name = "待确认供应商" if placeholder_vendor else _vendor_name(product, index)
        required_tags = ["material_gate_failed"]
        if social_source:
            required_tags.append("source_reliability_risk")
        if placeholder_vendor:
            required_tags.append("subject_identity_gap")
        cases.append(
            ProcurementReviewEvalCase(
                case_id=f"source_{offset:02d}",
                scenario_type="analysis_source_identity",
                description=f"{product}主体或来源不可追溯",
                project=_project(blueprint=blueprint, budget_amount=190000 + offset * 11000),
                vendor=_vendor(
                    vendor_name=vendor_name,
                    source_platform="社交平台转发" if social_source else "合作伙伴口头推荐",
                    source_url=(
                        f"https://social.example.com/vendor/{offset:02d}"
                        if social_source
                        else f"https://partner-forward.example.com/{offset:02d}"
                    ),
                    contact_email=f"source{offset:02d}@vendor.example.com",
                    profile_summary="目前只有宣传截图、转发链接或二手介绍，缺少可直接核验的官网主体和正式产品资料。",
                    procurement_notes="业务想先让采购判断是否值得继续沟通，但当前主体名称或来源链路不足以支撑准入。",
                    handles_company_data=False,
                    requires_system_integration=False,
                    quoted_amount=160000 + offset * 7000,
                    focus_points="重点核实主体身份、官网来源和正式材料，不建议仅凭转发信息推进。",
                ),
                expected=_expected(
                    required_analysis_tags=tuple(required_tags),
                    forbidden_analysis_tags=("data_handling_risk", "system_integration_risk"),
                    required_missing_materials=(),
                    forbidden_missing_materials=("安全问卷或安全白皮书", "数据处理说明或隐私/DPA材料", "数据存储/部署/数据流说明", "安全事件通知承诺"),
                    acceptable_titles=(TITLE_ONBOARDING, TITLE_BACKGROUND, TITLE_FAQ),
                ),
            )
        )
    return cases


def _capability_gap_cases() -> list[ProcurementReviewEvalCase]:
    cases: list[ProcurementReviewEvalCase] = []
    for offset, blueprint in enumerate(CASE_BLUEPRINTS[:15]):
        index = offset + 90
        _department, product, _scenario, _value = blueprint
        budget = 210000 + offset * 10000
        cases.append(
            ProcurementReviewEvalCase(
                case_id=f"capability_{offset:02d}",
                scenario_type="analysis_capability_gap",
                description=f"{product}能力描述明显泛化",
                project=_project(blueprint=blueprint, budget_amount=budget),
                vendor=_vendor(
                    vendor_name=_vendor_name(product, index),
                    source_platform="官网",
                    source_url=f"https://generic{offset:02d}.example.com",
                    contact_email=f"capability{offset:02d}@vendor.example.com",
                    profile_summary="供应商主打通用表单、审批流、任务看板和组织协作，介绍材料没有覆盖本项目关键业务对象和专业功能。",
                    procurement_notes="业务只提供了泛化介绍，采购需要提醒业务补充功能对照，而不是只因为它是软件平台就继续推进。",
                    handles_company_data=False,
                    requires_system_integration=False,
                    quoted_amount=round(budget * 0.86, 2),
                    focus_points="关注产品能力是否真正匹配当前采购目标，尤其是是否存在只买到通用协作工具的风险。",
                ),
                expected=_expected(
                    required_analysis_tags=("business_fit_gap",),
                    forbidden_analysis_tags=("material_gate_failed", "source_reliability_risk", "subject_identity_gap", "data_handling_risk", "system_integration_risk"),
                    required_missing_materials=(),
                    forbidden_missing_materials=COMMON_FORBIDDEN_MISSING,
                    acceptable_titles=(TITLE_SERVICE, TITLE_ONBOARDING, TITLE_FAQ),
                ),
            )
        )
    return cases


PROCUREMENT_REVIEW_EVAL_CASES: tuple[ProcurementReviewEvalCase, ...] = tuple(
    _clean_cases()
    + _budget_attention_cases()
    + _data_review_cases()
    + _source_identity_cases()
    + _capability_gap_cases()
)

if len(PROCUREMENT_REVIEW_EVAL_CASES) != 100:
    raise RuntimeError(f"Expected 100 procurement review cases, got {len(PROCUREMENT_REVIEW_EVAL_CASES)}")
