import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:vaultvoiceapp/main.dart';
import 'package:vaultvoiceapp/models/case_model.dart';
import 'package:vaultvoiceapp/core/storage/secure_store.dart';

void main() {
  testWidgets('home exposes survivor support and recovery actions', (
    tester,
  ) async {
    await tester.pumpWidget(const ProviderScope(child: VaultVoiceApp()));
    expect(find.text('Get support'), findsOneWidget);
    expect(find.text('Open my case'), findsOneWidget);
  });

  testWidgets('fresh case starts with one clarification question', (
    tester,
  ) async {
    final model = CaseModel.fromJson({
      'case_id': 'VV-TEST',
      'clarifying_questions': ['Are you safe right now?'],
      'clarifying_qa': [],
      'analysis_status': 'complete',
    });
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ClarificationScreen(store: SecureStore(), caseModel: model),
        ),
      ),
    );
    expect(find.text('Question 1 of 5'), findsOneWidget);
    expect(find.text('Are you safe right now?'), findsOneWidget);
    expect(find.text('Your answer'), findsOneWidget);
  });

  testWidgets('empty clarification response opens the conclusion screen', (
    tester,
  ) async {
    final model = CaseModel.fromJson({
      'case_id': 'VV-TEST',
      'clarifying_questions': [],
      'clarifying_qa': [],
      'analysis_status': 'complete',
      'severity': 'low',
      'ai_legal_summary': 'Keep a private record and seek support.',
    });
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: SupportPlanScreen(store: SecureStore(), caseModel: model),
        ),
      ),
    );
    expect(find.text('Your support plan'), findsOneWidget);
    expect(
      find.text('Keep a private record and seek support.'),
      findsOneWidget,
    );
    expect(find.text('See support matches'), findsOneWidget);
  });
}
