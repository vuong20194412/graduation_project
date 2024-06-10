from django.templatetags.static import static
from django.utils import timezone
from django.http.response import HttpResponse
import datetime

URL_JS = r"\static\users\js\tz_sub_utc_minutes.js"


class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.TZ_SUB_UTC_MINUTES = 'tsum'  # 'tz_sub_utc_minutes'
        with open(file=__file__[:__file__.rfind('\\')] + URL_JS, mode='w', encoding='utf-8') as f:
            f.write('\nfunction getCookie(name) {'
                    '\n\tconst parts=`; ${document.cookie}`.split(`; ${name}=`);'
                    '\n\tif (parts.length >= 2) {'
                    '\n\t\tconst value = parts.pop().split(";").shift();'
                    '\n\t\treturn value;'
                    '\n\t}'
                    '\n}')
            f.write('\nfunction update_tsum(tsum_cookie_name) {'
                    '\n\tif (!getCookie(tsum_cookie_name)) {'
                    '\n\t\tconst cookies = document.cookie;'
                    '\n\t\tdocument.cookie =`${tsum_cookie_name}=${-(new Date()).getTimezoneOffset()};path="/";secure`;'
                    '\n\t\tif(!getCookie(tsum_cookie_name)) {'
                    '\n\t\t\tdocument.write("<h1>Vui lòng bật cookie và tải lại.</h1>")'
                    '\n\t\t}'
                    '\n\t\telse {'
                    '\n\t\t\tlocation.reload();'
                    '\n\t\t}'
                    '\n\t}'
                    '\n\telse if (getCookie(tsum_cookie_name) != -(new Date()).getTimezoneOffset()) {'
                    '\n\t\tconst cookies = document.cookie;'
                    '\n\t\tdocument.cookie =`${tsum_cookie_name}=${-(new Date()).getTimezoneOffset()};path="/";secure`;'
                    '\n\t\tlocation.reload();'
                    '\n\t}'
                    '\n}')
            f.write('\nupdate_tsum("{}");'.format(self.TZ_SUB_UTC_MINUTES))

    def __call__(self, request):
        tz_sub_utc_minutes = request.COOKIES.get(self.TZ_SUB_UTC_MINUTES)
        if tz_sub_utc_minutes:
            try:
                tz_sub_utc_minutes = int(tz_sub_utc_minutes)
                timezone.activate(datetime.timezone(datetime.timedelta(minutes=tz_sub_utc_minutes)))
            except ValueError:
                timezone.activate(datetime.timezone.utc)
        else:
            timezone.activate(datetime.timezone.utc)
        response = self.get_response(request)
        if isinstance(response, HttpResponse):
            contenttype = response.headers.get('Content-Type')
            if not contenttype:
                contenttype = response.headers.get('content-type')
                if not contenttype:
                    if request.path.endswith(".png"):
                        contenttype = 'image/png'
                    if request.path.endswith(".jpg") or request.path.endswith(".jpeg"):
                        contenttype = 'image/jpg'
                response.headers['Content-Type'] = contenttype
            if 'text/html' in contenttype:
                response.content = (f'<script src={static("users/js/tz_sub_utc_minutes.js")}>'
                                    f'</script>').encode() + response.content
                # browser must not store html
                response.headers['Cache-Control'] = 'no-store'
        return response
