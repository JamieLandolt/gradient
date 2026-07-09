/** Shared response shapes mirroring the backend schemas. */

export interface Course {
  id: number
  code: string
  title: string
  units: number
  description: string
}

export interface Program {
  id: number
  code: string
  title: string
  total_units: number
  required_courses: string[]
  elective_courses: string[]
}

export interface EnrolmentSummary {
  enrolment_id: number
  course_code: string
  course_title: string
  units: number
  year: number
  semester: string
  status: 'planned' | 'in_progress' | 'completed'
  final_grade: number | null
  final_percent: number | null
  is_transfer: boolean
}

export interface AssessmentRow {
  id: number
  source: 'profile' | 'custom'
  name: string
  weight: number
  max_mark: number
  due_date: string | null
  hurdle_min_percent: number | null
  hurdle_description: string | null
  score: number | null
}

export interface Standing {
  enrolment_id: number
  secured_percent: number
  remaining_weight: number
  best_case_percent: number
  worst_case_percent: number
  projected_percent: number | null
  projected_grade: number | null
  items: AssessmentRow[]
}

export interface RequiredMarks {
  target_grade: number
  target_percent: number
  status: 'reachable' | 'already_secured' | 'not_reachable' | 'locked'
  required_average_percent: number | null
  per_item: { name: string; weight: number; required_percent: number }[]
  hurdle_blocked: boolean
  hurdle_warnings: string[]
  final_percent: number | null
  final_grade: number | null
}

export interface GpaSummary {
  gpa: number | null
  completed_courses: number
  total_units: number
}

export interface PrereqStatusRow {
  course_code: string
  course_title: string
  requirement_kind: 'required' | 'elective'
  is_completed: boolean
  prereq_status: 'met' | 'partially_met' | 'not_met'
  outstanding: string[]
  requires_manual_check: boolean
  raw_prerequisite: string | null
}

export interface PlanSequence {
  feasible: boolean
  semesters: {
    year: number
    semester: string
    label: string
    entries: { course_code: string; units: number; explanation: string }[]
  }[]
  diagnostics: { severity: string; message: string }[]
}

export interface RecommendationSet {
  id?: number
  generated_at?: string | null
  provider: string
  items: {
    course_code: string
    rank: number
    reason: string
    prereq_status: string
  }[]
  disclaimer: string
}

export interface RecommendationSummary {
  id: number
  provider: string
  generated_at: string | null
  item_count: number
}

export interface StudyPlan {
  id?: number
  generated_at?: string | null
  provider: string
  course_code: string
  target_grade: number
  required_average_percent: number | null
  target_status: string | null
  sessions: {
    session_date: string
    duration_minutes: number
    focus: string
    assessment_name?: string
  }[]
  disclaimer: string
}

export interface StudyPlanSummary {
  id: number
  course_code: string | null
  target_grade: number
  provider: string
  generated_at: string | null
}

export interface DegreePlanSummary {
  id: number
  name: string
  feasible: boolean
  generated_at: string | null
}

export interface SavedDegreePlan {
  id: number
  name: string
  feasible: boolean
  generated_at: string | null
  semesters: PlanSequence['semesters']
  diagnostics: PlanSequence['diagnostics']
}

export interface SearchResult {
  course_id: number
  code: string
  title: string
  description: string
  similarity: number
}

export interface UserProgramLink {
  position: number
  programs: { id: number; code: string; title: string; total_units: number }
}
