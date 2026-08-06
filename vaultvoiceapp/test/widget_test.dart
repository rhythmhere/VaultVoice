import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:vaultvoiceapp/main.dart';

void main() {
  testWidgets('home exposes survivor support and recovery actions', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: VaultVoiceApp()));
    expect(find.text('Get support'), findsOneWidget);
    expect(find.text('Open my case'), findsOneWidget);
  });
}
