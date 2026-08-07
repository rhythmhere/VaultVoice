import 'dart:async';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/theme/app_theme.dart';
import 'core/storage/secure_store.dart';
import 'core/network/dio_client.dart';
import 'repositories/vault_repository.dart';
import 'models/case_model.dart';
import 'widgets/safety_bar.dart';
import 'screens/sos/sos_sheet.dart';

final storeProvider = Provider((_) => SecureStore());
final repoProvider = Provider(
  (ref) => VaultRepository(
    DioClient(ref.watch(storeProvider)),
    ref.watch(storeProvider),
  ),
);
VaultRepository refRepo(SecureStore store) =>
    VaultRepository(DioClient(store), store);
void main() => runApp(const ProviderScope(child: VaultVoiceApp()));

class VaultVoiceApp extends StatelessWidget {
  const VaultVoiceApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    initialRoute: '/',
    routes: {
      '/': (_) => const HomeScreen(),
      '/neutral': (_) => const NeutralScreen(),
      '/report': (_) => const ReportScreen(),
      '/recover': (_) => const RecoveryScreen(),
    },
    theme: AppTheme.data,
    debugShowCheckedModeBanner: false,
  );
}

class Frame extends StatelessWidget {
  const Frame({
    super.key,
    required this.title,
    required this.child,
    required this.store,
  });
  final String title;
  final Widget child;
  final SecureStore store;
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Row(
        children: [
          const Icon(Icons.security_outlined, size: 24),
          const SizedBox(width: 9),
          Text(title),
        ],
      ),
      actions: [SafetyBar(store: store)],
    ),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 680),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 22, 20, 50),
            child: child,
          ),
        ),
      ),
    ),
  );
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final store = SecureStore();
    return Frame(
      store: store,
      title: 'VaultVoice',
      child: ListView(
        children: [
          const SizedBox(height: 28),
          Text(
            'Your story, in your own time.',
            style: Theme.of(context).textTheme.headlineMedium,
          ),
          const SizedBox(height: 12),
          const Text(
            'Understand what happened, organize what you remember, and explore your options without creating an account or sharing your identity.',
          ),
          const SizedBox(height: 28),
          FilledButton.icon(
            onPressed: () => Navigator.pushNamed(context, '/report'),
            icon: const Icon(Icons.edit_document),
            label: const Text('Get support'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => Navigator.pushNamed(context, '/recover'),
            icon: const Icon(Icons.lock_open_outlined),
            label: const Text('Open my case'),
          ),
          const SizedBox(height: 32),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.shield_outlined, color: AppTheme.primary),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      'No account needed. Your case stays private, and you can write in English or Nepali.',
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'For immediate danger, call Nepal Police on 100 or Khabar Garaun / NWC on 1145. This app is not an emergency response service.',
          ),
        ],
      ),
    );
  }
}

class NeutralScreen extends StatelessWidget {
  const NeutralScreen({super.key});
  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: Text('Notes')));
}

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key});
  @override
  State<ReportScreen> createState() => _ReportState();
}

class _ReportState extends State<ReportScreen> {
  String category = 'Domestic violence';
  bool danger = false, busy = false;
  final district = TextEditingController(text: 'Kathmandu');
  final report = TextEditingController();
  @override
  Widget build(BuildContext context) {
    final store = SecureStore();
    return Frame(
      store: store,
      title: 'Get support',
      child: ListView(
        children: [
          Text(
            'You can take this one step at a time.',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 20),
          DropdownButtonFormField<String>(
            initialValue: category,
            items: const [
              'Domestic violence',
              'Harassment',
              'Sexual violence',
              'Online abuse',
              'Other',
            ].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(),
            onChanged: (x) => setState(() => category = x!),
            decoration: const InputDecoration(
              labelText: 'What kind of support do you need?',
            ),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: district,
            decoration: const InputDecoration(labelText: 'District'),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: report,
            maxLines: 7,
            decoration: const InputDecoration(
              labelText: 'What would you like to share?',
            ),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('I may be in immediate danger'),
            subtitle: const Text(
              'This only prioritizes your support information. It does not contact emergency services.',
            ),
            value: danger,
            onChanged: (x) => setState(() => danger = x),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: busy
                ? null
                : () async {
                    if (report.text.trim().isEmpty) return;
                    setState(() => busy = true);
                    try {
                      final c = await refRepo(store).create(
                        category: category,
                        district: district.text,
                        report: report.text,
                        emergency: danger,
                      );
                      if (context.mounted) showCaseCreated(context, store, c);
                    } catch (_) {
                      if (mounted) setState(() => busy = false);
                    }
                  },
            child: Text(busy ? 'Saving...' : 'Create my private case'),
          ),
        ],
      ),
    );
  }
}

void showCaseCreated(BuildContext context, SecureStore store, dynamic c) {
  showDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => AlertDialog(
      title: const Text('Your recovery key'),
      content: SelectableText(
        'Case ID: ${c.id}\n\nKeep this Case ID somewhere private. It is needed to open your case again.',
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.pop(context);
            openCaseAfterCreation(context, store, c as CaseModel);
          },
          child: const Text('Continue'),
        ),
      ],
    ),
  );
}

void openCaseAfterCreation(
  BuildContext context,
  SecureStore store,
  CaseModel caseModel,
) {
  Navigator.pushReplacement(
    context,
    MaterialPageRoute(
      builder: (_) => caseModel.questions.isEmpty
          ? SupportPlanScreen(store: store, caseModel: caseModel)
          : ClarificationScreen(store: store, caseModel: caseModel),
    ),
  );
}

class RecoveryScreen extends StatefulWidget {
  const RecoveryScreen({super.key});
  @override
  State<RecoveryScreen> createState() => _RecoveryState();
}

class _RecoveryState extends State<RecoveryScreen> {
  final id = TextEditingController();
  bool busy = false;
  @override
  Widget build(BuildContext context) {
    final store = SecureStore();
    return Frame(
      store: store,
      title: 'Open my case',
      child: ListView(
        children: [
          Text(
            'Use your Case ID',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          const Text(
            'Your Case ID is the recovery key. It is not a password, so keep it private.',
          ),
          const SizedBox(height: 20),
          TextField(
            controller: id,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(labelText: 'VV-XXXXXXXX'),
          ),
          const SizedBox(height: 14),
          FilledButton(
            onPressed: busy
                ? null
                : () async {
                    final navigator = Navigator.of(context);
                    setState(() => busy = true);
                    try {
                      final c = await refRepo(store).login(id.text);
                      if (!mounted) return;
                      openRecoveredCase(navigator.context, store, c);
                    } catch (_) {
                      if (mounted) setState(() => busy = false);
                    }
                  },
            child: Text(busy ? 'Opening...' : 'Open my case'),
          ),
        ],
      ),
    );
  }
}

void openRecoveredCase(
  BuildContext context,
  SecureStore store,
  CaseModel caseModel,
) {
  Navigator.pushReplacement(
    context,
    MaterialPageRoute(
      builder: (_) => caseModel.questions.isEmpty
          ? CaseScreen(store: store, caseModel: caseModel)
          : ClarificationScreen(store: store, caseModel: caseModel),
    ),
  );
}

class ClarificationScreen extends StatefulWidget {
  const ClarificationScreen({
    super.key,
    required this.store,
    required this.caseModel,
  });
  final SecureStore store;
  final CaseModel caseModel;
  @override
  State<ClarificationScreen> createState() => _ClarificationState();
}

class _ClarificationState extends State<ClarificationScreen> {
  late CaseModel caseModel;
  final answer = TextEditingController();
  bool busy = false;

  @override
  void initState() {
    super.initState();
    caseModel = widget.caseModel;
  }

  @override
  void dispose() {
    answer.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final text = answer.text.trim();
    if (text.isEmpty || busy || caseModel.questions.isEmpty) return;
    setState(() => busy = true);
    try {
      final response = await refRepo(
        widget.store,
      ).clarify(caseModel.id, caseModel.questions.first, text);
      final next =
          ((response['next_questions'] ??
                      response['clarifying_questions'] ??
                      [])
                  as List)
              .cast<String>();
      final updated = caseModel.copyWith(
        questions: next,
        clarifyingQa: ((response['clarifying_qa'] ?? []) as List)
            .map((e) => Map<String, dynamic>.from(e))
            .toList(),
        summary: response['ai_legal_summary'] as String?,
        severity: response['severity'] as String?,
        analysisStatus: response['analysis_status'] as String?,
      );
      if (!mounted) return;
      if (next.isEmpty) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (_) =>
                SupportPlanScreen(store: widget.store, caseModel: updated),
          ),
        );
      } else {
        setState(() {
          caseModel = updated;
          answer.clear();
          busy = false;
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() => busy = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Your answer could not be saved: $error')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final asked = caseModel.clarifyingQa.length;
    return Frame(
      store: widget.store,
      title: 'A few gentle questions',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Question ${asked + 1} of 5',
            style: Theme.of(context).textTheme.labelLarge,
          ),
          const SizedBox(height: 6),
          LinearProgressIndicator(value: ((asked + 1) / 5).clamp(0.0, 1.0)),
          const SizedBox(height: 22),
          if (caseModel.clarifyingQa.isNotEmpty) ...[
            Text(
              'Earlier answers',
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 18),
            ...caseModel.clarifyingQa.map(
              (item) => Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item['question']?.toString() ?? ''),
                      const SizedBox(height: 6),
                      Text(
                        item['answer']?.toString() ?? '',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 18),
          ],
          Text(
            caseModel.questions.first,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 18),
          TextField(
            controller: answer,
            minLines: 4,
            maxLines: 8,
            enabled: !busy,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Your answer'),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: busy ? null : _submit,
              icon: const Icon(Icons.send_outlined),
              label: Text(busy ? 'Saving answer...' : 'Continue'),
            ),
          ),
        ],
      ),
    );
  }
}

class SupportPlanScreen extends StatefulWidget {
  const SupportPlanScreen({
    super.key,
    required this.store,
    required this.caseModel,
  });
  final SecureStore store;
  final CaseModel caseModel;
  @override
  State<SupportPlanScreen> createState() => _SupportPlanState();
}

class _SupportPlanState extends State<SupportPlanScreen> {
  late CaseModel caseModel;
  bool retrying = false;
  @override
  void initState() {
    super.initState();
    caseModel = widget.caseModel;
  }

  Future<void> _retry() async {
    setState(() => retrying = true);
    try {
      final updated = await refRepo(widget.store).retryAnalysis(caseModel.id);
      if (mounted)
        setState(() {
          caseModel = updated;
          retrying = false;
        });
    } catch (error) {
      if (mounted) {
        setState(() => retrying = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Analysis is still unavailable: $error')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final unavailable =
        caseModel.analysisStatus == 'failed' ||
        caseModel.analysisStatus == 'unavailable';
    return Frame(
      store: widget.store,
      title: 'Your support plan',
      child: ListView(
        children: [
          Text(
            'Your next steps',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          const Text(
            'Here is a calm first overview based on what you shared. This is general information, not formal legal advice.',
          ),
          const SizedBox(height: 20),
          Card(
            child: ListTile(
              leading: const Icon(Icons.priority_high),
              title: const Text('Safety signal'),
              subtitle: Text(caseModel.severity ?? 'Pending'),
            ),
          ),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Plain-language guidance',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text(caseModel.summary ?? 'Your guidance is being prepared.'),
                ],
              ),
            ),
          ),
          Card(
            child: const ListTile(
              leading: Icon(Icons.phone_in_talk),
              title: Text('Immediate help'),
              subtitle: Text(
                'If danger is immediate, call Nepal Police on 100 or Khabar Garaun on 1145.',
              ),
            ),
          ),
          if (unavailable) ...[
            const SizedBox(height: 8),
            const Text(
              'Your report and answers are saved. Analysis is temporarily unavailable.',
              style: TextStyle(color: AppTheme.danger),
            ),
            OutlinedButton.icon(
              onPressed: retrying ? null : _retry,
              icon: const Icon(Icons.refresh),
              label: Text(retrying ? 'Trying again...' : 'Try analysis again'),
            ),
          ],
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: () => Navigator.pushReplacement(
              context,
              MaterialPageRoute(
                builder: (_) => MatchesScreen(
                  store: widget.store,
                  caseModel: caseModel,
                  initialFlow: true,
                ),
              ),
            ),
            icon: const Icon(Icons.arrow_forward),
            label: const Text('See support matches'),
          ),
        ],
      ),
    );
  }
}

class CaseScreen extends StatelessWidget {
  const CaseScreen({super.key, required this.store, required this.caseModel});
  final SecureStore store;
  final dynamic caseModel;

  @override
  Widget build(BuildContext context) => Frame(
    store: store,
    title: 'My support space',
    child: ListView(
      children: [
        const StatusBadge('approved'),
        const SizedBox(height: 14),
        Text('Your case', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  caseModel.id,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                  ),
                ),
                const SizedBox(height: 14),
                InfoTile(
                  label: 'Severity',
                  value: caseModel.severity ?? 'Being reviewed',
                ),
                InfoTile(
                  label: 'Case status',
                  value: caseModel.status ?? 'Open',
                ),
              ],
            ),
          ),
        ),
        if (caseModel.analysisStatus == 'failed' ||
            caseModel.analysisStatus == 'unavailable')
          const InfoTile(
            label: 'Support plan',
            value:
                'Your saved case is safe. Analysis is temporarily unavailable.',
          ),
        const SizedBox(height: 12),
        if (caseModel.questions.isNotEmpty)
          FilledButton.icon(
            onPressed: () => showClarify(context, store, caseModel),
            icon: const Icon(Icons.question_answer_outlined),
            label: const Text('Continue questions'),
          ),
        const SizedBox(height: 8),
        FilledButton.icon(
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) =>
                  CaseToolsScreen(store: store, caseModel: caseModel),
            ),
          ),
          icon: const Icon(Icons.dashboard_outlined),
          label: const Text('Open all case tools'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => showReferral(context, store, caseModel),
          icon: const Icon(Icons.volunteer_activism_outlined),
          label: const Text('Support organizations'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) =>
                  CrowdfundingScreen(store: store, caseModel: caseModel),
            ),
          ),
          icon: const Icon(Icons.volunteer_activism_outlined),
          label: const Text('Request crowdfunding'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: () => showSosSheet(context, store),
          icon: const Icon(Icons.sos, color: AppTheme.danger),
          label: const Text('Emergency support'),
        ),
      ],
    ),
  );
}

class InfoTile extends StatelessWidget {
  const InfoTile({super.key, required this.label, required this.value});
  final String label, value;
  @override
  Widget build(BuildContext context) => ListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(label),
    subtitle: Text(value),
    leading: const Icon(Icons.check_circle_outline),
  );
}

void showClarify(BuildContext context, SecureStore store, dynamic c) {
  final answer = TextEditingController();
  showDialog(
    context: context,
    builder: (_) => AlertDialog(
      title: const Text('One question at a time'),
      content: TextField(
        controller: answer,
        maxLines: 5,
        decoration: InputDecoration(labelText: c.questions.first),
      ),
      actions: [
        TextButton(
          onPressed: () async {
            Navigator.pop(context);
            await refRepo(store).clarify(c.id, c.questions.first, answer.text);
          },
          child: const Text('Save answer'),
        ),
      ],
    ),
  );
}

void showReferral(BuildContext context, SecureStore store, dynamic c) {
  bool consent = false;
  showDialog(
    context: context,
    builder: (_) => StatefulBuilder(
      builder: (context, set) => AlertDialog(
        title: const Text('Before you contact an organization'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Review exactly what will be shared. Choose the organization, sharing scope, message, and evidence items before submitting.',
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: consent,
                onChanged: (x) => set(() => consent = x ?? false),
                title: const Text('I explicitly consent to this referral'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: consent
                ? () {
                    Navigator.pop(context);
                  }
                : null,
            child: const Text('Continue'),
          ),
        ],
      ),
    ),
  );
}

class CrowdfundingScreen extends StatefulWidget {
  const CrowdfundingScreen({
    super.key,
    required this.store,
    required this.caseModel,
  });
  final SecureStore store;
  final CaseModel caseModel;

  @override
  State<CrowdfundingScreen> createState() => _CrowdfundingScreenState();
}

class _CrowdfundingScreenState extends State<CrowdfundingScreen> {
  late String caseStatus;
  late List<Map<String, dynamic>> requests;
  late List<Map<String, dynamic>> campaigns;
  final amount = TextEditingController();
  final explanation = TextEditingController();
  String category = 'medical';
  bool publicConsent = false;
  bool busy = false;

  @override
  void initState() {
    super.initState();
    caseStatus = widget.caseModel.status ?? 'open';
    requests = List<Map<String, dynamic>>.from(
      widget.caseModel.crowdfundingRequests,
    );
    campaigns = List<Map<String, dynamic>>.from(
      widget.caseModel.crowdfundingCampaigns,
    );
  }

  @override
  void dispose() {
    amount.dispose();
    explanation.dispose();
    super.dispose();
  }

  bool get eligible =>
      caseStatus == 'ngo_contacted' || caseStatus == 'resolved';

  @override
  Widget build(BuildContext context) {
    final request = requests.isEmpty ? null : requests.last;
    final campaign = campaigns.isEmpty ? null : campaigns.first;
    return Frame(
      store: widget.store,
      title: 'Crowdfunding',
      child: ListView(
        children: [
          Text(
            'Community support',
            style: Theme.of(context).textTheme.labelLarge,
          ),
          const SizedBox(height: 8),
          Text(
            'Request crowdfunding',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 8),
          const Text(
            'Request an administrator review a fundraising campaign for costs related to your case.',
          ),
          const SizedBox(height: 18),
          if (campaign != null) _campaignCard(campaign),
          if (campaign == null && request != null) _requestCard(request),
          if (campaign == null && request == null) _requestForm(),
        ],
      ),
    );
  }

  Widget _requestCard(Map<String, dynamic> request) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: Text('Request status')),
              Chip(label: Text(_label(request['status']))),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'NPR ${request['requested_amount'] ?? ''} · ${request['category'] ?? ''}',
          ),
          if ((request['review_note'] ?? '').toString().isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(request['review_note'].toString()),
          ] else ...[
            const SizedBox(height: 10),
            const Text('An administrator is reviewing your request.'),
          ],
        ],
      ),
    ),
  );

  Widget _campaignCard(Map<String, dynamic> campaign) => Card(
    child: Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: Text('Your campaign is live')),
              Chip(label: Text(_label(campaign['status']))),
            ],
          ),
          const SizedBox(height: 10),
          Text(campaign['description']?.toString() ?? ''),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text(
                  'Your approved campaign is available on the public crowdfunding page.',
                ),
              ),
            ),
            icon: const Icon(Icons.open_in_new),
            label: const Text('Campaign approved'),
          ),
        ],
      ),
    ),
  );

  Widget _requestForm() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (!eligible) ...[
        Card(
          child: ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('Available after NGO contact'),
            subtitle: const Text(
              'An NGO or administrator must contact your case before you can request crowdfunding.',
            ),
          ),
        ),
        const SizedBox(height: 12),
        if (caseStatus == 'open')
          OutlinedButton.icon(
            onPressed: busy ? null : _markNgoContacted,
            icon: const Icon(Icons.handshake_outlined),
            label: const Text('Mark NGO contacted'),
          ),
      ] else ...[
        DropdownButtonFormField<String>(
          initialValue: category,
          decoration: const InputDecoration(labelText: 'Need category'),
          items: const [
            DropdownMenuItem(value: 'medical', child: Text('Medical')),
            DropdownMenuItem(value: 'legal', child: Text('Legal')),
            DropdownMenuItem(value: 'shelter', child: Text('Shelter')),
            DropdownMenuItem(value: 'education', child: Text('Education')),
            DropdownMenuItem(value: 'relocation', child: Text('Relocation')),
            DropdownMenuItem(value: 'other', child: Text('Other')),
          ],
          onChanged: busy
              ? null
              : (value) => setState(() => category = value ?? category),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Amount in NPR'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: explanation,
          minLines: 4,
          maxLines: 7,
          decoration: const InputDecoration(
            labelText: 'Why is funding needed?',
          ),
        ),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: publicConsent,
          onChanged: busy
              ? null
              : (value) => setState(() => publicConsent = value ?? false),
          title: const Text('Allow anonymous public display'),
        ),
        FilledButton.icon(
          onPressed: busy ? null : _submit,
          icon: const Icon(Icons.arrow_forward),
          label: Text(busy ? 'Submitting...' : 'Submit request'),
        ),
      ],
    ],
  );

  Future<void> _markNgoContacted() async {
    setState(() => busy = true);
    try {
      await refRepo(widget.store).status(widget.caseModel.id, 'ngo_contacted');
      if (mounted)
        setState(() {
          caseStatus = 'ngo_contacted';
          busy = false;
        });
    } catch (error) {
      if (mounted) {
        setState(() => busy = false);
        _showError(error);
      }
    }
  }

  Future<void> _submit() async {
    final value = double.tryParse(amount.text.trim());
    if (value == null || value <= 0 || explanation.text.trim().length < 10) {
      _showError(
        'Enter a valid amount and at least 10 characters explaining the need.',
      );
      return;
    }
    setState(() => busy = true);
    try {
      final result = await refRepo(widget.store)
          .crowdfundingRequest(widget.caseModel.id, {
            'category': category,
            'requested_amount': value,
            'explanation': explanation.text.trim(),
            'consent_public_display': publicConsent,
          });
      if (!mounted) return;
      setState(() {
        requests.add(result);
        busy = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Crowdfunding request submitted for admin review.'),
        ),
      );
    } catch (error) {
      if (mounted) {
        setState(() => busy = false);
        _showError(error);
      }
    }
  }

  void _showError(Object error) => ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(error.toString().replaceFirst('Exception: ', ''))),
  );

  String _label(Object? value) =>
      (value?.toString() ?? 'pending').replaceAll('_', ' ');
}

class CaseToolsScreen extends StatelessWidget {
  const CaseToolsScreen({
    super.key,
    required this.store,
    required this.caseModel,
  });
  final SecureStore store;
  final dynamic caseModel;
  @override
  Widget build(BuildContext context) => Frame(
    store: store,
    title: 'Case tools',
    child: ListView(
      children: [
        Text(
          'Your private case space',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 8),
        const Text(
          'Choose what you want to review or add. Support organizations only see information after you explicitly consent.',
        ),
        const SizedBox(height: 20),
        _tool(
          context,
          Icons.description_outlined,
          'My report',
          'Review the report and support plan',
          () => showDialog(
            context: context,
            builder: (_) => AlertDialog(
              title: const Text('My report'),
              content: SingleChildScrollView(child: Text(caseModel.report)),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Close'),
                ),
              ],
            ),
          ),
        ),
        _tool(
          context,
          Icons.lock_outline,
          'Evidence vault',
          'Add, view, and download private evidence',
          () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) =>
                  EvidenceScreen(store: store, caseModel: caseModel),
            ),
          ),
        ),
        _tool(
          context,
          Icons.timeline_outlined,
          'Timeline',
          'Review evidence events and regenerate the timeline',
          () => showTimeline(context, store, caseModel),
        ),
        _tool(
          context,
          Icons.handshake_outlined,
          'Support matches and referrals',
          'Review verified organizations and referral status',
          () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => MatchesScreen(store: store, caseModel: caseModel),
            ),
          ),
        ),
        _tool(
          context,
          Icons.chat_bubble_outline,
          'Messages',
          'Chat after a referral exists; this screen checks with the server while visible',
          () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ChatScreen(store: store, caseModel: caseModel),
            ),
          ),
        ),
        _tool(
          context,
          Icons.volunteer_activism_outlined,
          'Support VaultVoice',
          'Optional platform donation',
          () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => DonationScreen(store: store)),
          ),
        ),
      ],
    ),
  );
  Widget _tool(
    BuildContext context,
    IconData icon,
    String title,
    String subtitle,
    VoidCallback tap,
  ) => ListTile(
    contentPadding: const EdgeInsets.symmetric(vertical: 6),
    leading: Icon(icon),
    title: Text(title),
    subtitle: Text(subtitle),
    trailing: const Icon(Icons.chevron_right),
    onTap: tap,
  );
}

void showTimeline(BuildContext context, SecureStore store, dynamic c) =>
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Evidence timeline'),
        content: SingleChildScrollView(
          child: Text(
            c.timeline.isEmpty
                ? 'No timeline events yet.'
                : c.timeline
                      .map((e) => '${e['date'] ?? ''}: ${e['summary'] ?? ''}')
                      .join('\n\n'),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
          TextButton(
            onPressed: () async {
              await refRepo(store).timeline(c.id);
              if (context.mounted) Navigator.pop(context);
            },
            child: const Text('Regenerate'),
          ),
        ],
      ),
    );

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.store, required this.caseModel});
  final SecureStore store;
  final dynamic caseModel;
  @override
  State<ChatScreen> createState() => _ChatState();
}

class _ChatState extends State<ChatScreen> {
  final input = TextEditingController();
  List<Map<String, dynamic>> items = [];
  bool loading = true;
  bool sending = false;
  late final Timer timer;
  @override
  void initState() {
    super.initState();
    _load();
    timer = Timer.periodic(const Duration(seconds: 15), (_) => _load());
  }

  Future<void> _load() async {
    try {
      final values = await refRepo(widget.store).messages(widget.caseModel.id);
      if (mounted)
        setState(() {
          items = values;
          loading = false;
        });
    } catch (_) {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  void dispose() {
    timer.cancel();
    input.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Frame(
    store: widget.store,
    title: 'Messages',
    child: Column(
      children: [
        if (loading) const LinearProgressIndicator(),
        Expanded(
          child: items.isEmpty
              ? const Center(
                  child: Text(
                    'Messages become available after a referral exists.',
                  ),
                )
              : ListView.builder(
                  itemCount: items.length,
                  itemBuilder: (_, i) => Align(
                    alignment: items[i]['sender_type'] == 'survivor'
                        ? Alignment.centerRight
                        : Alignment.centerLeft,
                    child: Container(
                      margin: const EdgeInsets.all(6),
                      padding: const EdgeInsets.all(12),
                      constraints: const BoxConstraints(maxWidth: 300),
                      decoration: BoxDecoration(
                        color: items[i]['sender_type'] == 'survivor'
                            ? const Color(0xffdcebea)
                            : Colors.white,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(items[i]['message'] ?? ''),
                    ),
                  ),
                ),
        ),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: input,
                minLines: 1,
                maxLines: 3,
                decoration: const InputDecoration(labelText: 'Message'),
              ),
            ),
            IconButton(
              onPressed: sending
                  ? null
                  : () async {
                      if (input.text.trim().isEmpty) return;
                      setState(() => sending = true);
                      await refRepo(
                        widget.store,
                      ).sendMessage(widget.caseModel.id, input.text.trim());
                      input.clear();
                      await _load();
                      if (mounted) setState(() => sending = false);
                    },
              icon: const Icon(Icons.send),
              tooltip: 'Send message',
            ),
          ],
        ),
      ],
    ),
  );
}

class EvidenceScreen extends StatefulWidget {
  const EvidenceScreen({
    super.key,
    required this.store,
    required this.caseModel,
  });
  final SecureStore store;
  final dynamic caseModel;
  @override
  State<EvidenceScreen> createState() => _EvidenceState();
}

class _EvidenceState extends State<EvidenceScreen> {
  bool uploading = false;
  double progress = 0;
  @override
  Widget build(BuildContext context) => Frame(
    store: widget.store,
    title: 'Evidence vault',
    child: ListView(
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.cloud_upload_outlined,
                  size: 42,
                  color: AppTheme.primary,
                ),
                const SizedBox(height: 10),
                const Text(
                  'Private evidence is encrypted by the service. Allowed types: JPG, PNG, WEBP, PDF, MP3, WAV, OGG, TXT.',
                ),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: uploading
                      ? null
                      : () async {
                          final picked = await FilePicker.platform.pickFiles(
                            withData: false,
                          );
                          if (picked == null ||
                              picked.files.single.path == null)
                            return;
                          setState(() {
                            uploading = true;
                            progress = 0;
                          });
                          try {
                            await refRepo(widget.store).uploadEvidence(
                              widget.caseModel.id,
                              picked.files.single,
                              onProgress: (sent, total) {
                                if (mounted && total > 0)
                                  setState(() => progress = sent / total);
                              },
                            );
                          } finally {
                            if (mounted) setState(() => uploading = false);
                          }
                        },
                  icon: const Icon(Icons.upload_file),
                  label: Text(
                    uploading
                        ? 'Uploading ${(progress * 100).round()}%'
                        : 'Add evidence',
                  ),
                ),
                if (uploading)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: LinearProgressIndicator(value: progress),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Files in your vault',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        ...widget.caseModel.evidence.map<Widget>(
          (item) => Card(
            child: ListTile(
              leading: const Icon(Icons.lock_outline, color: AppTheme.primary),
              title: Text(item['name'] ?? 'Evidence'),
              subtitle: Text(
                '${item['type'] ?? ''}  ${item['size'] ?? ''} bytes',
              ),
              trailing: IconButton(
                onPressed: () async {
                  await refRepo(
                    widget.store,
                  ).downloadEvidence(widget.caseModel.id, item['id'] as int);
                  if (context.mounted)
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Evidence retrieved securely.'),
                      ),
                    );
                },
                icon: const Icon(Icons.download),
                tooltip: 'Download',
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

class MatchesScreen extends StatefulWidget {
  const MatchesScreen({
    super.key,
    required this.store,
    required this.caseModel,
    this.initialFlow = false,
  });
  final SecureStore store;
  final CaseModel caseModel;
  final bool initialFlow;
  @override
  State<MatchesScreen> createState() => _MatchesState();
}

class _MatchesState extends State<MatchesScreen> {
  List<Map<String, dynamic>> matches = [];
  late CaseModel caseModel;
  bool loaded = false;
  @override
  void initState() {
    super.initState();
    caseModel = widget.caseModel;
    _load();
  }

  Future<void> _load() async {
    try {
      final value = await refRepo(widget.store).matches(widget.caseModel.id);
      if (mounted)
        setState(() {
          matches = value;
          caseModel = caseModel.copyWith(matches: value);
          loaded = true;
        });
    } catch (_) {
      if (mounted) setState(() => loaded = true);
    }
  }

  @override
  Widget build(BuildContext context) => Frame(
    store: widget.store,
    title: 'Support matches',
    child: ListView(
      children: [
        if (!loaded) const LinearProgressIndicator(),
        ...matches.map(
          (org) => Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(16),
              leading: const CircleAvatar(
                backgroundColor: AppTheme.primaryPale,
                child: Icon(Icons.handshake_outlined, color: AppTheme.primary),
              ),
              title: Text(org['name'] ?? 'Organization'),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(org['description'] ?? ''),
              ),
              trailing: FilledButton(
                onPressed: () => _consent(context, org),
                child: const Text('Review'),
              ),
            ),
          ),
        ),
        if (loaded && widget.initialFlow) ...[
          const SizedBox(height: 18),
          const Text(
            'You can review a match now or return to it later from your case dashboard.',
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: () => Navigator.pushReplacement(
              context,
              MaterialPageRoute(
                builder: (_) =>
                    CaseScreen(store: widget.store, caseModel: caseModel),
              ),
            ),
            icon: const Icon(Icons.dashboard_outlined),
            label: const Text('Open my case dashboard'),
          ),
        ],
      ],
    ),
  );
  void _consent(BuildContext context, Map<String, dynamic> org) {
    bool consent = false;
    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (context, set) => AlertDialog(
          title: Text('Referral to ${org['name']}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                'Sharing scope: contact details, evidence summary, and the message you provide. No evidence is included unless you select it.',
              ),
              CheckboxListTile(
                value: consent,
                onChanged: (v) => set(() => consent = v ?? false),
                title: const Text('I explicitly consent'),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: consent
                  ? () async {
                      await refRepo(
                        widget.store,
                      ).referral(widget.caseModel.id, {
                        'ngo_id': org['id'],
                        'consent_scope': 'contact_details_evidence_summary',
                        'submitted_message': 'I am requesting support.',
                        'consent_confirmed': true,
                        'includes_evidence': false,
                        'evidence_refs': [],
                      });
                      if (context.mounted) Navigator.pop(context);
                    }
                  : null,
              child: const Text('Submit referral'),
            ),
          ],
        ),
      ),
    );
  }
}

class DonationScreen extends StatefulWidget {
  const DonationScreen({super.key, required this.store});
  final SecureStore store;
  @override
  State<DonationScreen> createState() => _DonationState();
}

class _DonationState extends State<DonationScreen> {
  final amount = TextEditingController(text: '500');
  bool anonymous = true, busy = false;
  @override
  Widget build(BuildContext context) => Frame(
    store: widget.store,
    title: 'Support VaultVoice',
    child: ListView(
      children: [
        const Text(
          'Your donation supports private access to support. Payment-provider confirmation happens outside this app.',
        ),
        const SizedBox(height: 20),
        TextField(
          controller: amount,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Amount in NPR'),
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: anonymous,
          onChanged: (v) => setState(() => anonymous = v),
          title: const Text('Give anonymously'),
        ),
        FilledButton(
          onPressed: busy
              ? null
              : () async {
                  setState(() => busy = true);
                  try {
                    await refRepo(widget.store).donate(
                      amount: double.parse(amount.text),
                      anonymous: anonymous,
                    );
                    if (context.mounted)
                      showDialog(
                        context: context,
                        builder: (_) => const AlertDialog(
                          title: Text('Thank you'),
                          content: Text(
                            'Your donation intent is ready for payment-provider confirmation.',
                          ),
                        ),
                      );
                  } catch (_) {}
                  if (mounted) setState(() => busy = false);
                },
          child: Text(busy ? 'Preparing...' : 'Continue to payment'),
        ),
      ],
    ),
  );
}
