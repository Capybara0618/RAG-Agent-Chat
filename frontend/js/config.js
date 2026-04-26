export const API_BASE_URL = window.location.origin;

export const NAV_ITEMS = {
  business: [
    {
      id: "overview",
      title: "总览",
      description: "查看我方发起项目、退回原因和当前推进状态。",
    },
    {
      id: "projects",
      title: "业务申请",
      description: "创建草稿、提交申请、撤回修改。",
    },
  ],
  manager: [
    {
      id: "overview",
      title: "总览",
      description: "查看待审批项目、关键风险和阶段进展。",
    },
    {
      id: "projects",
      title: "审批工作台",
      description: "处理上级审批和项目推进。",
    },
  ],
  procurement: [
    {
      id: "overview",
      title: "总览",
      description: "查看待比选项目、候选供应商和驳回回流。",
    },
    {
      id: "projects",
      title: "采购执行",
      description: "维护候选供应商、AI 准入评审和送法务。",
    },
    {
      id: "assistant",
      title: "审查助手",
      description: "发起供应商 Agent 准入审查。",
    },
  ],
  legal: [
    {
      id: "overview",
      title: "总览",
      description: "查看待法务项目、合同往返和风险提示。",
    },
    {
      id: "projects",
      title: "法务审查",
      description: "上传合同材料、审查条款并退回采购。",
    },
    {
      id: "assistant",
      title: "审查助手",
      description: "查询合同红线、条款差异和合规要点。",
    },
  ],
  admin: [
    {
      id: "overview",
      title: "总览",
      description: "查看全平台流程、风险、归档和系统状态。",
    },
    {
      id: "projects",
      title: "项目归档",
      description: "查看全量项目、签署归档和历史留痕。",
    },
    {
      id: "knowledge",
      title: "知识库",
      description: "上传制度、模板、合同红线和 FAQ。",
    },
    {
      id: "assistant",
      title: "审查助手",
      description: "检查问答表现和引用证据。",
    },
    {
      id: "audit",
      title: "审计评测",
      description: "查看 Trace、评测结果和系统复盘。",
    },
  ],
};

export const DEMO_ACCOUNTS = [
  { username: "business", password: "business", role: "business", label: "业务发起部门" },
  { username: "manager", password: "manager", role: "manager", label: "上级审核" },
  { username: "procurement", password: "procurement", role: "procurement", label: "采购部门" },
  { username: "legal", password: "legal", role: "legal", label: "法务部门" },
  { username: "admin", password: "admin", role: "admin", label: "管理员" },
];

export const DEMO_QUESTIONS = [
  "这个采购申请的目的、预算和上线时间说明还缺什么？",
  "从需求审批角度看，这个项目是否有必要采购？",
  "请总结 AlphaDesk 的询价、比价和采购订单方案还缺哪些条件？",
  "对比标准 MSA 和供应商红线版本，哪些条款需要升级给法务复核？",
  "在正式签署前，这个项目还缺哪些审批或归档动作？",
];

export const DEMO_FILES = [
  "采购核心-供应商准入办法.md",
  "采购核心-采购审批矩阵.md",
  "采购核心-安全评审操作流程.md",
  "采购核心-常见问答.csv",
  "法务核心-数据处理供应商检查清单.md",
  "法务核心-合同审查红线指引.md",
  "法务核心-标准主服务协议模板.md",
  "法务核心-供应商回传红线协议.md",
];

export const PROJECT_STAGE_ORDER = [
  "business_draft",
  "manager_review",
  "procurement_sourcing",
  "legal_review",
  "signing",
  "completed",
];

export const PROJECT_REVIEW_PRESETS = {
  manager_review: "请从部门负责人 / 管理层角度判断，这个采购需求是否有必要，预算是否合理，还缺什么审批信息？",
  procurement_sourcing: "请基于供应商资料、准入要求和线上采集信息，判断这家公司是否适合作为供应商，并给出风险点。",
  legal_review: "请对比我方采购合同与对方回传修改版，指出合法合规风险、缺失条款和是否建议退回采购重新筛选。",
  final_approval: "请结合采购执行结果和法务结论，指出这个项目在最终审批与签署前还缺哪些必备批准或条件。",
  signing: "请列出这个项目在线下执行、下单、签署与归档阶段还需要完成的收尾动作。",
};

const LABELS = {
  business_draft: "业务申请",
  qa: "知识问答",
  compare: "对比审查",
  workflow: "流程判断",
  support: "支持判断",
  knowledge_qa: "知识问答",
  procurement_fit_review: "供应商匹配度审查",
  legal_contract_review: "合同审查",
  answer: "直接回答",
  clarify: "需要澄清",
  refuse: "拒绝回答",
  indexed: "已完成索引",
  completed: "已完成",
  success: "成功",
  done: "已完成",
  provided: "已提供",
  approved: "已批准",
  submitted: "已提交",
  updated: "已更新",
  active: "进行中",
  cancelled: "已取消",
  failed: "失败",
  withdrawn: "已撤回",
  candidate: "候选",
  shortlisted: "入围",
  selected: "已选中",
  rejected: "已淘汰",
  legal_rejected: "法务驳回",
  recommend_proceed: "材料齐备，可推进",
  review_with_risks: "存在风险，需升级复核",
  reject_irrelevant_materials: "材料无关，未进入审查",
  needs_required_materials: "材料不全，待补充",
  fit_proceed: "适合推进",
  fit_needs_info: "基本适合，需补信息",
  fit_escalate: "风险较高，需升级复核",
  fit_reject: "不适合推进",
  collect_info: "补充信息",
  escalate_review: "升级复核",
  manual_confirmation: "进入人工确认",
  replace_vendor: "更换供应商",
  needs_follow_up: "需补充跟进",
  approve: "建议通过",
  return: "建议退回采购",
  suggest_legal_review: "建议转法务",
  hold_for_procurement: "先由采购复核",
  wait_for_more_materials: "先补充材料",
  pass: "通过",
  warn: "关注",
  fail: "高风险",
  info: "仅提示",
  returned_to_legal_review: "退回法务",
  returned_to_procurement_sourcing: "退回采购",
  returned_by_final_approval: "被终审退回",
  high: "高风险",
  open: "待处理",
  uploaded: "已上传",
  indexing: "索引中",
  medium: "中风险",
  pending: "待处理",
  missing: "缺失",
  low: "低风险",
  business: "业务部门",
  manager: "上级",
  procurement: "采购部门",
  legal: "法务部门",
  admin: "管理员",
  internal: "内部",
  outbound: "对外发送",
  inbound: "对方回传",
  manager_review: "上级审批",
  procurement_sourcing: "采购比选",
  legal_review: "法务审查",
  legal_contract_review: "法务合同审查",
  final_approval: "最终审批",
  signing: "签署归档",
};

export function navItemsFor(role) {
  return NAV_ITEMS[role] || NAV_ITEMS.business;
}

export function toneOf(value) {
  if (!value) return "neutral";
  if (
    [
      "indexed",
      "completed",
      "answer",
      "success",
      "done",
      "provided",
      "approved",
      "active",
      "selected",
      "recommend_proceed",
      "fit_proceed",
      "approve",
      "submitted",
      "pass",
    ].includes(value)
  ) {
    return "success";
  }
  if (
    [
      "failed",
      "refuse",
      "rejected",
      "high",
      "return",
      "open",
      "legal_rejected",
      "withdrawn",
      "cancelled",
      "fail",
      "reject_irrelevant_materials",
      "fit_reject",
      "replace_vendor",
    ].includes(value)
  ) {
    return "danger";
  }
  if (
    [
      "uploaded",
      "indexing",
      "clarify",
      "medium",
      "pending",
      "missing",
      "shortlisted",
      "review_with_risks",
      "fit_needs_info",
      "fit_escalate",
      "needs_required_materials",
      "needs_follow_up",
      "collect_info",
      "escalate_review",
      "manual_confirmation",
      "candidate",
      "warn",
      "info",
      "suggest_legal_review",
      "wait_for_more_materials",
    ].includes(
      value,
    )
  ) {
    return "warn";
  }
  return "neutral";
}

export function stageText(stage) {
  return LABELS[stage] || (stage || "").replaceAll("_", " ");
}

export function displayLabel(value) {
  return LABELS[value] || value || "-";
}


