import {
  BookOpen,
  Clapperboard,
  Film,
  FolderKanban,
  LayoutDashboard,
  Library,
  Settings,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

export type NavGroup = "创作" | "生产" | "系统";

export interface NavItem {
  /** Route path, relative to the hash router root. */
  path: string;
  label: string;
  icon: LucideIcon;
  description: string;
  group: NavGroup;
  /** Which product milestone ships this module (plan §20). */
  milestone: "V1.0" | "V1.5" | "V2.0";
  /** Modules beyond the current milestone render an "not yet implemented" state. */
  implemented: boolean;
  /** Short capability list shown on the placeholder screen. */
  features?: string[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    path: "/",
    label: "工作台",
    icon: LayoutDashboard,
    description: "项目总览、创作进度与系统状态",
    group: "创作",
    milestone: "V1.0",
    implemented: true,
  },
  {
    path: "/projects",
    label: "项目管理",
    icon: FolderKanban,
    description: "新建、打开与管理小说项目",
    group: "创作",
    milestone: "V1.0",
    implemented: true,
  },
  {
    path: "/editor",
    label: "小说创作",
    icon: BookOpen,
    description: "大纲、分卷、章节与 AI 续写",
    group: "创作",
    milestone: "V1.0",
    implemented: true,
  },
  {
    path: "/knowledge",
    label: "小说知识库",
    icon: Library,
    description: "全文检索、语义检索与记忆索引",
    group: "创作",
    milestone: "V1.0",
    implemented: false,
    features: [
      "FTS5 全文检索 + sqlite-vec 向量检索",
      "混合检索与 Reranker 重排",
      "分层记忆 L0–L4 与上下文组装",
      "增量索引与检索记录",
    ],
  },
  {
    path: "/characters",
    label: "世界观管理",
    icon: Users,
    description: "人物、关系、地点、势力与规则",
    group: "创作",
    milestone: "V1.0",
    implemented: false,
    features: [
      "人物设定、别名与实体消歧",
      "人物状态历史与关系图",
      "地点、势力、物品与能力体系",
      "时间线、事件与伏笔管理",
    ],
  },
  {
    path: "/storyboard",
    label: "故事板创作",
    icon: Clapperboard,
    description: "剧本解析、场景与镜头拆解",
    group: "生产",
    milestone: "V1.5",
    implemented: false,
    features: [
      "小说转剧本、剧本解析",
      "场景与镜头自动拆解",
      "角色与场景视觉一致性",
      "镜头提示词与生成状态",
    ],
  },
  {
    path: "/workflows",
    label: "工作流中心",
    icon: Workflow,
    description: "可视化工作流与任务调度",
    group: "生产",
    milestone: "V1.5",
    implemented: false,
    features: [
      "React Flow 节点编辑器",
      "工作流模板与运行",
      "任务队列、重试与日志",
      "暂停 / 恢复 / 断点续跑",
    ],
  },
  {
    path: "/media",
    label: "视频生产",
    icon: Film,
    description: "图片、视频、配音与成片合成",
    group: "生产",
    milestone: "V2.0",
    implemented: false,
    features: [
      "AI 图片与视频生成",
      "TTS 配音与字幕对齐",
      "镜头时间线与转场",
      "FFmpeg 合成与导出",
    ],
  },
  {
    path: "/settings",
    label: "系统设置",
    icon: Settings,
    description: "模型配置、存储与诊断",
    group: "系统",
    milestone: "V1.0",
    implemented: true,
  },
];

export const NAV_GROUPS: NavGroup[] = ["创作", "生产", "系统"];

export function findNavItem(pathname: string): NavItem | undefined {
  const exact = NAV_ITEMS.find((item) => item.path === pathname);
  if (exact) return exact;
  // Nested routes (e.g. /projects/proj_123) resolve to their parent entry.
  return NAV_ITEMS.filter((item) => item.path !== "/")
    .filter((item) => pathname.startsWith(`${item.path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0];
}