"""Sélection d’images résultat nouvelles par rapport à un instantané antérieur."""


def images_with_new_signatures(images, previous_signatures, signature_of):
    """Retourne les images dont la signature non vide n’était pas dans l’instantané."""
    previous_signatures = set(previous_signatures)
    fresh = []
    for image in images:
        signature = signature_of(image)
        if signature and signature not in previous_signatures:
            fresh.append(image)
    return fresh
