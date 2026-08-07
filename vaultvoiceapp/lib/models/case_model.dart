class CaseModel {
  const CaseModel({
    required this.id,
    this.category = '',
    this.district = '',
    this.report = '',
    this.severity,
    this.status,
    this.analysisStatus,
    this.summary,
    this.questions = const [],
    this.evidence = const [],
    this.matches = const [],
    this.timeline = const [],
    this.crowdfundingRequests = const [],
    this.crowdfundingCampaigns = const [],
  });
  final String id, category, district, report;
  final String? severity, status, analysisStatus, summary;
  final List<String> questions;
  final List<Map<String, dynamic>> evidence, matches, timeline;
  final List<Map<String, dynamic>> crowdfundingRequests, crowdfundingCampaigns;
  factory CaseModel.fromJson(Map<String, dynamic> j) => CaseModel(
    id: j['case_id'] as String,
    category: j['category'] ?? '',
    district: j['district'] ?? '',
    report: j['initial_report'] ?? '',
    severity: j['severity'],
    status: j['status'],
    analysisStatus: j['analysis_status'],
    summary: j['ai_legal_summary'],
    questions:
        ((j['clarifying_questions'] ?? j['next_questions'] ?? []) as List)
            .cast<String>(),
    evidence: ((j['evidence'] ?? []) as List)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    matches: ((j['matches'] ?? []) as List)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    timeline: ((j['timeline'] ?? []) as List)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    crowdfundingRequests: ((j['crowdfunding_requests'] ?? []) as List)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    crowdfundingCampaigns: ((j['crowdfunding_campaigns'] ?? []) as List)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
  );
}
