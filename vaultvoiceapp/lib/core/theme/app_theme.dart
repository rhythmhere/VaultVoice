import 'package:flutter/material.dart';

/// The single source of truth for the VaultVoice visual system.
class AppTheme {
  AppTheme._();

  // Core palette.
  static const vvPrimary = Color(0xff185c58);
  static const vvPrimaryHover = Color(0xff124a47);
  static const vvPrimaryPressed = Color(0xff0d3d3a);
  static const vvPrimaryContainer = Color(0xffd9eeeb);
  static const vvPrimaryDisabled = Color(0xff8fa8a5);
  static const vvOnPrimary = Color(0xffffffff);
  static const vvBackground = Color(0xfffcfaf7);
  static const vvSurface = Color(0xffffffff);
  static const vvSurfaceSubtle = Color(0xfff4f5f2);
  static const vvSurfaceMuted = Color(0xffecefec);
  static const vvTextPrimary = Color(0xff202525);
  static const vvTextSecondary = Color(0xff4d5956);
  static const vvTextDisabled = Color(0xff7c8784);
  static const vvBorder = Color(0xffb8c2be);
  static const vvBorderStrong = Color(0xff73807c);
  static const vvWhite = Color(0xffffffff);

  // Semantic palette.
  static const vvSuccess = Color(0xff176b43);
  static const vvSuccessContainer = Color(0xffddf3e6);
  static const vvWarning = Color(0xff755600);
  static const vvWarningContainer = Color(0xfffff1c9);
  static const vvError = Color(0xffa52a25);
  static const vvErrorContainer = Color(0xfffbe3e0);
  static const vvUrgent = Color(0xffb94a43);
  static const vvUrgentPressed = Color(0xff8f332f);
  static const vvUrgentContainer = Color(0xffffe5e1);
  static const vvInfo = Color(0xff28666a);
  static const vvInfoContainer = Color(0xffe0f1f0);

  // Approved layout tokens.
  static const space4 = 4.0;
  static const space8 = 8.0;
  static const space12 = 12.0;
  static const space14 = 14.0;
  static const space16 = 16.0;
  static const space20 = 20.0;
  static const space24 = 24.0;
  static const space32 = 32.0;
  static const space40 = 40.0;
  static const space48 = 48.0;
  static const space64 = 64.0;
  static const radius = 8.0;
  static const _shape = RoundedRectangleBorder(
    borderRadius: BorderRadius.all(Radius.circular(radius)),
  );
  static const _cardShape = RoundedRectangleBorder(
    side: BorderSide(color: vvBorder),
    borderRadius: BorderRadius.all(Radius.circular(radius)),
  );

  static const _fontFallback = <String>[
    'Noto Sans Devanagari',
    'Noto Sans',
    'sans-serif',
  ];

  static TextStyle _text({
    required double size,
    required FontWeight weight,
    required double height,
    Color color = vvTextPrimary,
  }) => TextStyle(
    fontFamily: 'Noto Sans',
    fontFamilyFallback: _fontFallback,
    fontSize: size,
    fontWeight: weight,
    height: height,
    letterSpacing: 0,
    color: color,
  );

  static ThemeData get data {
    const scheme = ColorScheme.light(
      primary: vvPrimary,
      onPrimary: vvOnPrimary,
      primaryContainer: vvPrimaryContainer,
      onPrimaryContainer: vvTextPrimary,
      secondary: vvInfo,
      onSecondary: vvWhite,
      secondaryContainer: vvInfoContainer,
      onSecondaryContainer: vvTextPrimary,
      surface: vvSurface,
      onSurface: vvTextPrimary,
      surfaceContainerHighest: vvSurfaceMuted,
      error: vvError,
      onError: vvWhite,
      errorContainer: vvErrorContainer,
      onErrorContainer: vvTextPrimary,
      outline: vvBorder,
      outlineVariant: vvSurfaceMuted,
    );
    final textTheme = TextTheme(
      displayLarge: _text(size: 32, weight: FontWeight.w700, height: 1.2),
      headlineLarge: _text(size: 28, weight: FontWeight.w700, height: 1.25),
      headlineMedium: _text(size: 32, weight: FontWeight.w700, height: 1.2),
      headlineSmall: _text(size: 28, weight: FontWeight.w700, height: 1.25),
      titleLarge: _text(size: 22, weight: FontWeight.w700, height: 1.3),
      titleMedium: _text(size: 18, weight: FontWeight.w700, height: 1.35),
      bodyLarge: _text(size: 17, weight: FontWeight.w400, height: 1.55),
      bodyMedium: _text(size: 15, weight: FontWeight.w400, height: 1.55),
      bodySmall: _text(
        size: 14,
        weight: FontWeight.w400,
        height: 1.5,
        color: vvTextSecondary,
      ),
      labelLarge: _text(size: 15, weight: FontWeight.w700, height: 1.35),
      labelMedium: _text(size: 13, weight: FontWeight.w700, height: 1.35),
      labelSmall: _text(
        size: 12,
        weight: FontWeight.w400,
        height: 1.45,
        color: vvTextSecondary,
      ),
    );
    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: scheme,
      fontFamily: 'Noto Sans',
      fontFamilyFallback: _fontFallback,
      scaffoldBackgroundColor: vvBackground,
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: <TargetPlatform, PageTransitionsBuilder>{
          TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
          TargetPlatform.iOS: FadeForwardsPageTransitionsBuilder(),
        },
      ),
    );
    final buttonText = _text(size: 15, weight: FontWeight.w700, height: 1.35);
    final buttonShape = WidgetStatePropertyAll<OutlinedBorder>(_shape);
    final buttonPadding = WidgetStatePropertyAll<EdgeInsetsGeometry>(
      const EdgeInsets.symmetric(horizontal: space16, vertical: space12),
    );
    return base.copyWith(
      textTheme: textTheme,
      appBarTheme: AppBarTheme(
        backgroundColor: vvBackground,
        foregroundColor: vvTextPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: _text(size: 22, weight: FontWeight.w700, height: 1.3),
      ),
      cardTheme: const CardThemeData(
        color: vvSurface,
        elevation: 0,
        margin: EdgeInsets.only(bottom: space12),
        shape: _cardShape,
        clipBehavior: Clip.antiAlias,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(Size(0, space48)),
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: WidgetStatePropertyAll(buttonText),
          backgroundColor: WidgetStateProperty.resolveWith(
            (states) => states.contains(WidgetState.disabled)
                ? vvPrimaryDisabled
                : states.contains(WidgetState.pressed)
                ? vvPrimaryPressed
                : vvPrimary,
          ),
          foregroundColor: const WidgetStatePropertyAll(vvOnPrimary),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(Size(0, space48)),
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: WidgetStatePropertyAll(buttonText),
          foregroundColor: WidgetStateProperty.resolveWith(
            (states) => states.contains(WidgetState.disabled)
                ? vvTextDisabled
                : vvPrimary,
          ),
          backgroundColor: WidgetStateProperty.resolveWith(
            (states) => states.contains(WidgetState.pressed)
                ? vvPrimaryContainer
                : states.contains(WidgetState.disabled)
                ? vvSurfaceSubtle
                : vvSurface,
          ),
          side: WidgetStateProperty.resolveWith(
            (states) => BorderSide(
              color: states.contains(WidgetState.disabled)
                  ? vvBorder
                  : vvPrimary,
            ),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: ButtonStyle(
          minimumSize: const WidgetStatePropertyAll(Size(0, space48)),
          padding: buttonPadding,
          shape: buttonShape,
          textStyle: WidgetStatePropertyAll(buttonText),
          foregroundColor: const WidgetStatePropertyAll(vvPrimary),
          overlayColor: const WidgetStatePropertyAll(vvPrimaryContainer),
        ),
      ),
      inputDecorationTheme: const InputDecorationTheme(
        filled: true,
        fillColor: vvSurface,
        floatingLabelBehavior: FloatingLabelBehavior.always,
        contentPadding: EdgeInsets.symmetric(
          horizontal: space16,
          vertical: space14,
        ),
        labelStyle: TextStyle(
          fontFamily: 'Noto Sans',
          fontSize: 15,
          fontWeight: FontWeight.w700,
          color: vvTextPrimary,
        ),
        hintStyle: TextStyle(color: vvTextSecondary),
        border: OutlineInputBorder(
          borderSide: BorderSide(color: vvBorder),
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
        enabledBorder: OutlineInputBorder(
          borderSide: BorderSide(color: vvBorder),
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
        focusedBorder: OutlineInputBorder(
          borderSide: BorderSide(color: vvPrimary, width: 2),
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
        errorBorder: OutlineInputBorder(
          borderSide: BorderSide(color: vvError),
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderSide: BorderSide(color: vvError, width: 2),
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
        disabledBorder: OutlineInputBorder(
          borderSide: BorderSide(color: vvBorder),
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: vvSurface,
        selectedColor: vvPrimaryContainer,
        disabledColor: vvSurfaceSubtle,
        side: const BorderSide(color: vvBorder),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(radius)),
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: space8,
          vertical: space4,
        ),
        labelStyle: _text(size: 13, weight: FontWeight.w700, height: 1.35),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: vvSurface,
        surfaceTintColor: Colors.transparent,
        insetPadding: const EdgeInsets.all(space24),
        shape: _shape,
        titleTextStyle: _text(size: 18, weight: FontWeight.w700, height: 1.35),
        contentTextStyle: _text(
          size: 17,
          weight: FontWeight.w400,
          height: 1.55,
        ),
      ),
      dividerTheme: const DividerThemeData(color: vvBorder, thickness: 1),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: vvPrimary,
        linearTrackColor: vvSurfaceMuted,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: vvTextPrimary,
        contentTextStyle: _text(
          size: 15,
          weight: FontWeight.w400,
          height: 1.55,
          color: vvWhite,
        ),
        shape: _shape,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  static String _normalize(String? value) =>
      (value ?? 'pending').toLowerCase().replaceAll('_', '-');

  static Color statusColor(String? value, {String domain = 'generic'}) {
    final status = _normalize(value);
    if ((domain == 'case' && (status == 'urgent' || status == 'high-risk')) ||
        (domain == 'sos' && status == 'ready')) {
      return vvUrgentPressed;
    }
    if (status == 'resolved' ||
        status == 'closed' ||
        status == 'accepted' ||
        status == 'approved' ||
        status == 'uploaded' ||
        status == 'encrypted' ||
        status == 'verified' ||
        status == 'sent' ||
        status == 'acknowledged') {
      return vvSuccess;
    }
    if (status == 'rejected' || status == 'cancelled' || status == 'failed') {
      return vvError;
    }
    if (status == 'in-progress' ||
        status == 'forwarded' ||
        status == 'new' ||
        status == 'open') {
      return vvInfo;
    }
    return vvWarning;
  }

  static Color statusBackground(String? value, {String domain = 'generic'}) {
    final foreground = statusColor(value, domain: domain);
    if (foreground == vvSuccess) return vvSuccessContainer;
    if (foreground == vvError) return vvErrorContainer;
    if (foreground == vvInfo) return vvInfoContainer;
    if (foreground == vvUrgentPressed) return vvUrgentContainer;
    return vvWarningContainer;
  }
}

class StatusBadge extends StatelessWidget {
  const StatusBadge(this.value, {super.key, this.domain = 'generic'});
  final String? value;
  final String domain;

  @override
  Widget build(BuildContext context) => Container(
    constraints: const BoxConstraints(minHeight: 24),
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: AppTheme.statusBackground(value, domain: domain),
      borderRadius: BorderRadius.circular(AppTheme.radius),
    ),
    child: Text(
      (value ?? 'pending').replaceAll('_', ' '),
      style: Theme.of(context).textTheme.labelMedium?.copyWith(
        color: AppTheme.statusColor(value, domain: domain),
      ),
    ),
  );
}
