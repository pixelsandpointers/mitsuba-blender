
def get_references(mi_props):
    """Return (name, ref_id) pairs from a Properties object.

    Handles mitsuba 3.8+ where named_references() was replaced by references(),
    and where inline children may be stored as Properties.Reference values under
    their own ID as the key (scene children) or under semantic keys like 'bsdf'.
    """
    # mitsuba < 3.8
    try:
        return list(mi_props.named_references())
    except AttributeError:
        pass

    import mitsuba as mi

    # references() covers explicit <ref> elements
    refs = list(mi_props.references())
    if refs:
        return refs

    # Fallback: scan all items for Reference-typed values only.
    result = []
    for key, value in mi_props.items():
        if isinstance(value, mi.Properties.Reference):
            ref_id = value.id() if hasattr(value, 'id') else getattr(value, 'name', key)
            result.append((key, ref_id))
        elif isinstance(value, mi.Properties.ResolvedReference):
            result.append((key, key))
    return result


def named_references_with_class(mi_context, mi_props, cls):
    result = []
    for _, ref_id in get_references(mi_props):
        props = mi_context.mi_scene_props.get_with_id_and_class(ref_id, cls)
        if props is not None:
            result.append(props)
    return result
