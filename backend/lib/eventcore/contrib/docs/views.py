from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def graph_view(request):
    """Serve the portable interactive documentation UI."""
    prefix = (settings.URL_PREFIX or "").strip("/")
    api_base = f"/{prefix}/api/eventcore" if prefix else "/api/eventcore"
    return render(
        request,
        "eventcore_docs/graph.html",
        {
            "graph_api_url": f"{api_base}/graph",
        },
    )
