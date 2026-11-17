// 后端 app/schemas.py 的返回形状，只写前端用到的字段。
// 只做接口描述，不放请求函数：请求仍走 api/client.ts 与 api/stream.ts。

export type AnswerMode = 'voice' | 'typed' | 'mixed'
export type AsrSource = 'cloud' | 'browser'
export type InputMode = 'voice' | 'typed'
export type ReportSource = 'llm' | 'mock'
export type SessionStatus = 'active' | 'finished'
export type TurnRole = 'ai' | 'user'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type WordScope = 'gaokao' | 'cet4' | 'cet6'

export interface UserOut {
  id: number
  username: string
  nickname?: string
}

export interface TokenOut {
  token: string
  user: UserOut
}

export interface SceneOut {
  id: string
  name: string
  icon: string
  desc: string
}

/** 目标里出现的关键词（Agent 用规则算达成，report 里用来核对） */
export interface SessionPlan {
  goals: string[]
  focus: string[]
  achieved: string[]
  missing: string[]
  rule_hits: string[]
  source: 'llm' | 'rule' | string
  review: string
  comment: string
}

export interface AudioMeta {
  duration_sec?: number | null
  speech_time_sec?: number | null
  pauses?: number[]
}

export interface KeyVocab {
  term: string
  zh?: string
}

/** POST /api/sessions 的请求体 */
export interface CreateSessionIn {
  scene_id: string
  difficulty?: Difficulty | string | null
  context?: string
  key_vocab?: KeyVocab[]
}

export interface CreateSessionOut {
  session_id: number
  opening_question: string
  plan: SessionPlan
}

/** POST /api/sessions/{id}/turn 与 /turn/stream 的请求体 */
export interface TurnIn {
  transcript: string
  audio?: AudioMeta | null
  input_mode?: InputMode | null
  asr_source?: AsrSource | null
}

export interface TurnOut {
  turn_index: number
  ai_reply: string
  is_follow_up: boolean
  should_finish: boolean
  degraded: boolean
  replaced: boolean
  flagged: boolean
  asr_source?: AsrSource | null
  plan: SessionPlan
}

export interface SessionTurnOut {
  id: number
  role: TurnRole
  content: string
  input_mode: InputMode
  asr_source?: AsrSource | null
  created_at: string
}

export interface SessionDetailOut {
  id: number
  scene_id: string
  scene_name: string
  difficulty: string
  status: SessionStatus
  created_at: string
  turns: SessionTurnOut[]
  report_id?: number | null
  total_score?: number | null
  plan: SessionPlan
}

export interface SentenceFix {
  original: string
  better: string
  reason: string
  error_type: 'spelling' | 'grammar' | 'stiffness' | 'wordiness' | string
  natural: string
  word: string
  related: Record<string, unknown>
  rule_ref: string
  rule?: Record<string, unknown> | null
}

export interface StudyItemOut {
  id: number
  kind: 'word' | 'phrase' | 'spelling' | string
  term: string
  context: string
  meaning_zh: string
  example: string
  related: Record<string, unknown>
  source_session_id?: number | null
  source: string
  reps: number
  lapses: number
  interval_days: number
  due_at: string
  due: boolean
  last_result?: string | null
  created_at: string
}

/** Agent 调用工具的一次记录（CoachPanel / AgentTrace / SSE tool 事件） */
export interface AgentTraceStep {
  step: number
  tool: string
  args: Record<string, unknown>
  ok: boolean
  ms: number
  summary: string
  result: string
}

export interface CoachEvidence {
  tool: string
  ref: string
}

export interface CoachPriority {
  fix_index: number
  title: string
  why: string
  evidence: CoachEvidence[]
  grounded: boolean
  next_step: string
}

/** 报告里的诊断教练；source=skipped 表示本次模型没给出结果 */
export interface CoachResult {
  priorities: CoachPriority[]
  summary?: string
  source?: 'llm' | 'skipped' | string
  trace?: AgentTraceStep[]
}

/** 报告页「AI 透明度」小卡 */
export interface ReportTransparency {
  model: string
  safety: { flagged_inputs: number; replaced_replies: number }
  scores: { model_ratio: number; rule_ratio: number } | null
  coach: { grounded: number; total: number } | null
}

export interface ReportOut {
  report_id: number
  total_score: number | null
  band: number | null
  cefr: string | null
  source: ReportSource
  mock_reason?: string | null
  answer_mode?: AnswerMode | null
  comparable_band?: number | null
  dimensions: Record<string, number>
  bands: Record<string, number>
  sentence_fixes: SentenceFix[]
  study_items: StudyItemOut[]
  comment: string
  features: Record<string, unknown>
  scoring_detail: Record<string, unknown>
  plan: SessionPlan
  coach?: CoachResult | null
  scales: Record<string, unknown>
  transparency?: ReportTransparency | null
  note: string
}

export interface HistoryItem {
  id: number
  scene_id: string
  scene_name: string
  status: SessionStatus
  report_id?: number | null
  total_score?: number | null
  band?: number | null
  cefr?: string | null
  comparable_band?: number | null
  answer_mode?: AnswerMode | null
  voice_turns: number
  typed_turns: number
  created_at: string
}

/** POST /api/scenes/from-image 的结果卡 */
export interface ImageSceneOut {
  scene_id: string
  scene_name: string
  context: string
  key_vocab: KeyVocab[]
  opening: string
}

export interface HintItem {
  en: string
  zh: string
  tag: string
}

export interface HintsOut {
  hints: HintItem[]
  source: 'llm' | 'frames'
  cached: boolean
}

export interface PreferencesOut {
  practice_difficulty: Difficulty
  word_scope: WordScope
  report_scale: string
}
