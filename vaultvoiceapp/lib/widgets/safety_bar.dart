import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../core/safe_exit/quick_exit.dart';
import '../core/storage/secure_store.dart';
import '../screens/sos/sos_sheet.dart';

class SafetyBar extends StatelessWidget {
  const SafetyBar({super.key, required this.store});
  final SecureStore store;
  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Tooltip(
        message: 'Quick Exit',
        child: IconButton(
          onPressed: () => QuickExit.run(context, store),
          icon: const Icon(Icons.exit_to_app),
          tooltip: 'Quick Exit',
        ),
      ),
      Tooltip(
        message: 'Emergency support',
        child: IconButton(
          onPressed: () => showSosSheet(context, store),
          icon: const Icon(Icons.sos, color: AppTheme.danger),
          tooltip: 'SOS',
        ),
      ),
    ],
  );
}
