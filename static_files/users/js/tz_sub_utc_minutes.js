
function getCookie(name) {
	const parts=`; ${document.cookie}`.split(`; ${name}=`);
	if (parts.length >= 2) {
		const value = parts.pop().split(";").shift();
		return value;
	}
}
function update_tsum(tsum_cookie_name) {
	if (!getCookie(tsum_cookie_name)) {
		const cookies = document.cookie;
		document.cookie =`${tsum_cookie_name}=${-(new Date()).getTimezoneOffset()};path="/";secure`;
		if(!getCookie(tsum_cookie_name)) {
			document.write("<h1>Vui lòng bật cookie và tải lại.</h1>")
		}
		else {
			location.reload();
		}
	}
	else if (getCookie(tsum_cookie_name) != -(new Date()).getTimezoneOffset()) {
		const cookies = document.cookie;
		document.cookie =`${tsum_cookie_name}=${-(new Date()).getTimezoneOffset()};path="/";secure`;
		location.reload();
	}
}
update_tsum("tsum");