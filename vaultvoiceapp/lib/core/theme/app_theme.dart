import 'package:flutter/material.dart';

/// Values mirror the public web frontend in styles.css. Mobile surfaces use
/// the repository's 8px maximum corner radius.
class AppTheme {
  static const bg = Color(0xfffcf9f8);
  static const surface = Color(0xffffffff);
  static const low = Color(0xfff6f3f2);
  static const container = Color(0xfff0eded);
  static const high = Color(0xffeae7e7);
  static const text = Color(0xff1b1c1c);
  static const muted = Color(0xff424845);
  static const primary = Color(0xff4b645a);
  static const primaryLight = Color(0xffa8c3b8);
  static const primaryPale = Color(0xffcde9dd);
  static const coral = Color(0xff865047);
  static const coralLight = Color(0xffffb8ad);
  static const coralPale = Color(0xffffdad4);
  static const line = Color(0xffc2c8c4);
  static const danger = Color(0xffba1a1a);
  static const radius = 8.0;

  static const _radius = BorderRadius.all(Radius.circular(radius));

  static ThemeData get data {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: primary,
          brightness: Brightness.light,
        ).copyWith(
          primary: primary,
          onPrimary: Colors.white,
          surface: surface,
          onSurface: text,
          error: danger,
          onError: Colors.white,
        );
    final base = ThemeData(useMaterial3: true, colorScheme: scheme);
    final typography = base.textTheme.apply(
      fontFamily: 'Quicksand',
      fontFamilyFallback: const [
        'Noto Sans Devanagari',
        'Noto Sans',
        'sans-serif',
      ],
    );
    return base.copyWith(
      scaffoldBackgroundColor: bg,
      textTheme: typography.copyWith(
        bodyLarge: const TextStyle(
          fontSize: 16,
          height: 1.5,
          fontWeight: FontWeight.w500,
          color: text,
        ),
        bodyMedium: const TextStyle(
          fontSize: 14,
          height: 1.5,
          fontWeight: FontWeight.w500,
          color: text,
        ),
        bodySmall: const TextStyle(
          fontSize: 13,
          height: 1.45,
          fontWeight: FontWeight.w500,
          color: muted,
        ),
        titleLarge: const TextStyle(
          fontSize: 24,
          height: 1.2,
          fontWeight: FontWeight.w700,
          color: primary,
        ),
        titleMedium: const TextStyle(
          fontSize: 18,
          height: 1.3,
          fontWeight: FontWeight.w700,
          color: primary,
        ),
        headlineSmall: const TextStyle(
          fontSize: 28,
          height: 1.2,
          fontWeight: FontWeight.w700,
          color: primary,
        ),
        headlineMedium: const TextStyle(
          fontSize: 32,
          height: 1.2,
          fontWeight: FontWeight.w700,
          color: primary,
        ),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: bg,
        foregroundColor: primary,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: 'Quicksand',
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: primary,
        ),
      ),
      cardTheme: const CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.only(bottom: 12),
        shape: RoundedRectangleBorder(borderRadius: _radius),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(Size(0, 48)),
          padding: const WidgetStatePropertyAll(
            EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          ),
          shape: const WidgetStatePropertyAll(
            RoundedRectangleBorder(borderRadius: _radius),
          ),
          textStyle: const WidgetStatePropertyAll(
            TextStyle(
              fontFamily: 'Quicksand',
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(Size(0, 48)),
          padding: const WidgetStatePropertyAll(
            EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          ),
          side: const WidgetStatePropertyAll(BorderSide(color: line)),
          shape: const WidgetStatePropertyAll(
            RoundedRectangleBorder(borderRadius: _radius),
          ),
          foregroundColor: const WidgetStatePropertyAll(primary),
          textStyle: const WidgetStatePropertyAll(
            TextStyle(
              fontFamily: 'Quicksand',
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: ButtonStyle(
          foregroundColor: const WidgetStatePropertyAll(primary),
          textStyle: const WidgetStatePropertyAll(
            TextStyle(
              fontFamily: 'Quicksand',
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: container,
        contentPadding: EdgeInsets.symmetric(horizontal: 18, vertical: 15),
        labelStyle: TextStyle(color: muted, fontWeight: FontWeight.w700),
        hintStyle: TextStyle(color: muted),
        border: OutlineInputBorder(
          borderSide: BorderSide.none,
          borderRadius: _radius,
        ),
        enabledBorder: OutlineInputBorder(
          borderSide: BorderSide.none,
          borderRadius: _radius,
        ),
        focusedBorder: OutlineInputBorder(
          borderSide: BorderSide(color: primary, width: 2),
          borderRadius: _radius,
        ),
        errorBorder: OutlineInputBorder(
          borderSide: BorderSide(color: danger, width: 1),
          borderRadius: _radius,
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderSide: BorderSide(color: danger, width: 2),
          borderRadius: _radius,
        ),
      ),
      dividerTheme: const DividerThemeData(color: line, thickness: 1),
      progressIndicatorTheme: const ProgressIndicatorThemeData(color: primary),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: text,
        contentTextStyle: TextStyle(color: Colors.white),
      ),
    );
  }

  static Color statusColor(String? value) {
    switch (value?.toLowerCase().replaceAll('_', '-')) {
      case 'resolved':
      case 'approved':
      case 'acknowledged':
        return const Color(0xff236944);
      case 'urgent':
      case 'high':
      case 'rejected':
        return const Color(0xff9b3026);
      case 'in-progress':
      case 'forwarded':
        return const Color(0xff2d6762);
      case 'pending':
      case 'requested':
      case 'admin-review':
      case 'on-hold':
        return const Color(0xff80611b);
      default:
        return muted;
    }
  }

  static Color statusBackground(String? value) {
    switch (value?.toLowerCase().replaceAll('_', '-')) {
      case 'resolved':
      case 'approved':
      case 'acknowledged':
        return const Color(0xffdff2e6);
      case 'urgent':
      case 'high':
      case 'rejected':
        return const Color(0xffffe3de);
      case 'in-progress':
      case 'forwarded':
        return const Color(0xffe1f0ef);
      case 'pending':
      case 'requested':
      case 'admin-review':
      case 'on-hold':
        return const Color(0xfffff1d1);
      default:
        return high;
    }
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge(this.value, {super.key});
  final String? value;
  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
    decoration: BoxDecoration(
      color: AppTheme.statusBackground(value),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      (value ?? 'pending').replaceAll('_', ' '),
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        color: AppTheme.statusColor(value),
      ),
    ),
  );
}
