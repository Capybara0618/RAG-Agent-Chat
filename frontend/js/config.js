export const API_BASE_URL = window.location.origin;

export const NAV_ITEMS = [
  {
    id: "overview",
    title: "\u603b\u89c8",
    description: "\u5e73\u53f0\u72b6\u6001\u3001\u4e0a\u624b\u5f15\u5bfc\u4e0e\u6700\u8fd1\u6d41\u7a0b\u6d3b\u52a8\u3002",
  },
  {
    id: "projects",
    title: "\u91c7\u8d2d\u9879\u76ee",
    description: "\u91c7\u8d2d\u6d41\u7a0b\u3001\u9636\u6bb5\u963b\u585e\u9879\u4e0e\u9879\u76ee\u7ea7 AI \u5ba1\u67e5\u3002",
  },
  {
    id: "knowledge",
    title: "\u77e5\u8bc6\u5e93",
    description: "\u4e0a\u4f20\u5236\u5ea6\u3001\u6a21\u677f\u3001\u7ea2\u7ebf\u5408\u540c\u3001SOP \u4e0e FAQ\u3002",
  },
  {
    id: "assistant",
    title: "\u5ba1\u67e5\u52a9\u624b",
    description: "\u72ec\u7acb\u95ee\u7b54\u5ba1\u67e5\uff0c\u67e5\u770b\u5f15\u7528\u3001\u8c03\u8bd5\u4fe1\u606f\u4e0e Trace\u3002",
  },
  {
    id: "audit",
    title: "\u5ba1\u8ba1\u8bc4\u6d4b",
    description: "\u67e5\u770b Trace\u3001\u8fd0\u884c\u8bc4\u6d4b\u3001\u590d\u76d8\u5931\u8d25\u6848\u4f8b\u3002",
  },
];

export const ROLE_OPTIONS = [
  { value: "guest", label: "\u4e1a\u52a1\u53d1\u8d77\u4eba" },
  { value: "employee", label: "\u91c7\u8d2d / \u5185\u90e8\u8bc4\u5ba1\u4eba" },
  { value: "admin", label: "\u5e73\u53f0\u7ba1\u7406\u5458" },
];

export const DEMO_QUESTIONS = [
  "\u4f9b\u5e94\u5546\u8fdb\u5165\u51c6\u5165\u6d41\u7a0b\u524d\uff0c\u5fc5\u987b\u5148\u51c6\u5907\u54ea\u4e9b\u6750\u6599\uff1f",
  "\u5bf9\u6bd4\u6807\u51c6 MSA \u548c\u4f9b\u5e94\u5546\u7ea2\u7ebf\u7248\u672c\uff0c\u54ea\u4e9b\u6761\u6b3e\u9700\u8981\u5347\u7ea7\u7ed9\u6cd5\u52a1\u590d\u6838\uff1f",
  "\u5b89\u5168\u8bc4\u5ba1\u6d41\u7a0b\u7684\u7b2c\u4e00\u6b65\u662f\u4ec0\u4e48\uff1f",
  "\u5728\u4ec0\u4e48\u60c5\u51b5\u4e0b\u91c7\u8d2d\u5fc5\u987b\u5347\u7ea7\u5230\u5ba1\u6279\u77e9\u9635\uff1f",
  "\u5982\u679c\u8d23\u4efb\u4e0a\u9650\u88ab\u5f31\u5316\uff0c\u8fd9\u4e2a\u9879\u76ee\u662f\u5426\u5fc5\u987b\u8fdb\u5165\u6cd5\u52a1\u5ba1\u67e5\uff1f",
];

export const DEMO_FILES = [
  "procurement_cn_vendor_onboarding_policy.md",
  "procurement_cn_contract_playbook.md",
  "procurement_cn_standard_msa_template.md",
  "procurement_cn_vendor_redline_msa.md",
  "procurement_cn_security_review_sop.md",
  "procurement_cn_approval_matrix.md",
  "procurement_cn_faq.csv",
];

export const PROJECT_STAGE_ORDER = [
  "draft",
  "vendor_onboarding",
  "security_review",
  "legal_review",
  "approval",
  "signing",
  "completed",
  "rejected",
];

export const PROJECT_REVIEW_PRESETS = {
  draft:
    "\u8bf7\u603b\u7ed3\u8fd9\u4e2a\u91c7\u8d2d\u9879\u76ee\u5728\u79bb\u5f00\u8349\u7a3f\u9636\u6bb5\u524d\uff0c\u8fd8\u7f3a\u5c11\u54ea\u4e9b\u5173\u952e\u4fe1\u606f\u6216\u52a8\u4f5c\u3002",
  vendor_onboarding:
    "\u4f9b\u5e94\u5546\u51c6\u5165\u7ee7\u7eed\u63a8\u8fdb\u524d\uff0c\u8fd8\u7f3a\u5c11\u54ea\u4e9b\u5fc5\u5907\u6750\u6599\u6216\u6761\u4ef6\uff1f",
  security_review:
    "\u5f53\u524d\u9879\u76ee\u5728\u5b89\u5168\u8bc4\u5ba1\u9636\u6bb5\u8fd8\u6709\u54ea\u4e9b\u963b\u585e\u9879\u548c\u98ce\u9669\u70b9\uff1f",
  legal_review:
    "\u8bf7\u5bf9\u6bd4\u8be5\u9879\u76ee\u7684\u6807\u51c6\u5408\u540c\u548c\u4f9b\u5e94\u5546\u7ea2\u7ebf\u7248\u672c\uff0c\u5e76\u6307\u51fa\u9700\u8981\u5347\u7ea7\u6cd5\u52a1\u7684\u6761\u6b3e\u3002",
  approval:
    "\u57fa\u4e8e\u5f53\u524d\u9879\u76ee\u4fe1\u606f\uff0c\u5728\u7b7e\u7f72\u524d\u8fd8\u7f3a\u5c11\u54ea\u4e9b\u5ba1\u6279\uff1f",
  signing:
    "\u5728\u6b63\u5f0f\u7b7e\u7f72\u5408\u540c\u524d\uff0c\u8fd8\u7f3a\u5c11\u54ea\u4e9b\u6700\u7ec8\u6750\u6599\u3001\u786e\u8ba4\u9879\u6216\u6536\u5c3e\u52a8\u4f5c\uff1f",
};

const LABELS = {
  qa: "\u77e5\u8bc6\u95ee\u7b54",
  compare: "\u5bf9\u6bd4\u5ba1\u67e5",
  workflow: "\u6d41\u7a0b\u5224\u65ad",
  support: "\u652f\u6301\u5224\u65ad",
  answer: "\u76f4\u63a5\u56de\u7b54",
  clarify: "\u9700\u8981\u6f84\u6e05",
  refuse: "\u62d2\u7edd\u56de\u7b54",
  indexed: "\u5df2\u5b8c\u6210\u7d22\u5f15",
  completed: "\u5df2\u5b8c\u6210",
  success: "\u6210\u529f",
  done: "\u5df2\u5b8c\u6210",
  provided: "\u5df2\u63d0\u4f9b",
  approved: "\u5df2\u6279\u51c6",
  active: "\u8fdb\u884c\u4e2d",
  failed: "\u5931\u8d25",
  rejected: "\u5df2\u9a73\u56de",
  high: "\u9ad8\u98ce\u9669",
  open: "\u5f85\u5904\u7406",
  uploaded: "\u5df2\u4e0a\u4f20",
  indexing: "\u7d22\u5f15\u4e2d",
  medium: "\u4e2d\u98ce\u9669",
  pending: "\u5f85\u5904\u7406",
  missing: "\u7f3a\u5931",
  low: "\u4f4e\u98ce\u9669",
  guest: "\u4e1a\u52a1\u53d1\u8d77\u4eba",
  employee: "\u91c7\u8d2d / \u5185\u90e8\u8bc4\u5ba1\u4eba",
  admin: "\u5e73\u53f0\u7ba1\u7406\u5458",
  draft: "\u8349\u7a3f",
  vendor_onboarding: "\u4f9b\u5e94\u5546\u51c6\u5165",
  security_review: "\u5b89\u5168\u8bc4\u5ba1",
  legal_review: "\u6cd5\u52a1\u5ba1\u67e5",
  approval: "\u5ba1\u6279\u4e2d",
  signing: "\u5f85\u7b7e\u7f72",
};

export function toneOf(value) {
  if (!value) return "neutral";
  if (
    ["indexed", "completed", "answer", "success", "done", "provided", "approved", "active"].includes(
      value,
    )
  ) {
    return "success";
  }
  if (["failed", "refuse", "rejected", "high", "open"].includes(value)) {
    return "danger";
  }
  if (["uploaded", "indexing", "clarify", "medium", "pending", "missing"].includes(value)) {
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
