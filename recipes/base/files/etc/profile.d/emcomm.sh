# emcommOS: expose /opt/emcomm binaries and desktop entries.
case ":${PATH}:" in
  *:/opt/emcomm/bin:*) ;;
  *) PATH="/opt/emcomm/bin:${PATH}" ;;
esac
export PATH
case ":${XDG_DATA_DIRS:-}:" in
  *:/opt/emcomm/share:*) ;;
  *) XDG_DATA_DIRS="/opt/emcomm/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" ;;
esac
export XDG_DATA_DIRS
