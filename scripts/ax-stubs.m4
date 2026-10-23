dnl Minimal stand-ins for the two autoconf-archive macros sane-backends'
dnl configure.ac uses, for building without that package (see build.sh).
dnl GCC defaults to C++17 already, and glibc's <stdint.h> is complete.
AC_DEFUN([AX_CXX_COMPILE_STDCXX_11], [HAVE_CXX11=1
AC_SUBST([HAVE_CXX11])])
AC_DEFUN([AX_CREATE_STDINT_H],
  [AC_CONFIG_COMMANDS([$1], [echo '#include <stdint.h>' > $1])])
