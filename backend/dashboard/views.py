from django.shortcuts import render


def overview(request):
    return render(request, "aerohealth/overview.html")


def weather_page(request):
    return render(request, "aerohealth/weather.html")


def prediction(request):
    return render(request, "aerohealth/prediction.html")


def account(request):
    return render(request, "aerohealth/account.html")


def login_page(request):
    return render(request, "aerohealth/auth.html", {"mode": "login"})


def signed_out(request):
    return render(request, "aerohealth/auth.html", {"mode": "out"})


def soon(title):
    """Placeholder for tabs whose design isn't built yet."""
    def view(request):
        return render(request, "aerohealth/soon.html", {"title": title})
    return view