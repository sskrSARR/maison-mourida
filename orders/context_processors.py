def cart(request):
    raw = {}
    if hasattr(request, "session"):
        raw = request.session.get("cart") or {}
    lines = raw.get("lines") or {}
    count = 0
    total = 0
    for line in lines.values():
        qty = int(line.get("qty", 0))
        count += qty
        total += qty * int(line.get("price", 0))
    return {"cart_count": count, "cart_total": total}
