import 'package:flutter/material.dart';
import '../storage/secure_store.dart';

class QuickExit {
  static Future<void> run(BuildContext context, SecureStore store) async {
    await store.clear();
    if (context.mounted)
      Navigator.of(context).pushNamedAndRemoveUntil('/neutral', (_) => false);
  }
}
