import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../core/storage/secure_store.dart';
import '../../core/safe_exit/quick_exit.dart';
import '../../core/theme/app_theme.dart';
import '../../main.dart';

Future<void> showSosSheet(BuildContext context, SecureStore store) =>
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.bg,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppTheme.radius),
        ),
      ),
      builder: (_) => SosSheet(store: store),
    );

class SosSheet extends StatefulWidget {
  const SosSheet({super.key, required this.store});
  final SecureStore store;
  @override
  State<SosSheet> createState() => _SosSheetState();
}

class _SosSheetState extends State<SosSheet> {
  final note = TextEditingController();
  Position? position;
  DateTime? locationCapturedAt;
  String location = 'No location shared';
  bool sending = false;

  Future<void> locate() async {
    try {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        _logLocationFailure('permission_denied', permission);
        setState(
          () => location =
              'Location permission was not granted. SOS can still be sent.',
        );
        return;
      }

      if (!await Geolocator.isLocationServiceEnabled()) {
        _logLocationFailure('service_disabled');
        setState(
          () => location =
              'Location services are disabled. SOS can still be sent.',
        );
        return;
      }

      final capturedPosition = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 15),
        ),
      );
      position = capturedPosition;
      locationCapturedAt = capturedPosition.timestamp;
      setState(() => location = 'Location ready to share');
    } catch (error, stackTrace) {
      final status = switch (error) {
        PermissionDeniedException() => 'permission_denied',
        LocationServiceDisabledException() => 'service_disabled',
        TimeoutException() => 'timeout',
        _ => 'unavailable',
      };
      _logLocationFailure(status, error, stackTrace);
      if (mounted) {
        setState(
          () => location = switch (status) {
            'permission_denied' =>
              'Location permission was not granted. SOS can still be sent.',
            'service_disabled' =>
              'Location services are disabled. SOS can still be sent.',
            'timeout' =>
              'Location took too long to respond. SOS can still be sent.',
            _ => 'Location unavailable. SOS can still be sent.',
          },
        );
      }
    }
  }

  void _logLocationFailure(
    String status, [
    Object? error,
    StackTrace? stackTrace,
  ]) {
    if (kDebugMode) {
      debugPrint(
        '[SOS] Location capture failed: $status${error == null ? '' : ' ($error)'}',
      );
      if (stackTrace != null) debugPrintStack(stackTrace: stackTrace);
    }
  }

  Future<void> send() async {
    setState(() => sending = true);
    try {
      final id = await widget.store.read(SecureStore.caseId);
      await refRepo(widget.store).sendSos(
        caseId: id,
        note: note.text.trim().isEmpty ? null : note.text.trim(),
        latitude: position?.latitude,
        longitude: position?.longitude,
        accuracy: position?.accuracy,
        locationStatus: position == null ? 'unavailable' : 'captured',
        capturedAt: locationCapturedAt,
      );
      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              position == null
                  ? 'SOS sent, location was unavailable.'
                  : 'SOS sent with your location.',
            ),
          ),
        );
      }
    } catch (_) {
      if (mounted) setState(() => sending = false);
    }
  }

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 12,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text(
                'Emergency support',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const Spacer(),
              IconButton(
                onPressed: () => QuickExit.run(context, widget.store),
                icon: const Icon(Icons.exit_to_app),
                tooltip: 'Quick Exit',
              ),
            ],
          ),
          const Text(
            'This app does not contact emergency services automatically.',
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => launchUrl(Uri.parse('tel:100')),
            icon: const Icon(Icons.phone),
            label: const Text('Call Nepal Police - 100'),
          ),
          OutlinedButton.icon(
            onPressed: () => launchUrl(Uri.parse('tel:1145')),
            icon: const Icon(Icons.phone),
            label: const Text('Call Khabar Garaun / NWC - 1145'),
          ),
          TextField(
            controller: note,
            maxLines: 2,
            decoration: const InputDecoration(labelText: 'Optional short note'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: locate,
            icon: const Icon(Icons.location_on_outlined),
            label: Text(location),
          ),
          const SizedBox(height: 8),
          FilledButton.icon(
            onPressed: sending ? null : send,
            icon: const Icon(Icons.sos),
            label: Text(sending ? 'Sending...' : 'Send SOS now'),
          ),
        ],
      ),
    ),
  );
}
