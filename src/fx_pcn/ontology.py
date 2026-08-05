from __future__ import annotations

from rdflib import Namespace

# Small custom ontology -- nothing standard covers "time-varying
# partial-correlation network," so this mints just the handful of terms that
# need it. The `.local` base IRIs match the convention the graph-nexus
# project already uses for its registered sources' `--base-iri` (e.g.
# https://strategic-reports.local/kg/), so this would slot in consistently
# if it were ever registered as a graph-nexus source -- not something this
# module does itself.
#
# Kept in its own module (rather than defined in rdf_export.py) so both
# rdf_export.py and macro_vocabulary.py can depend on it without a circular
# import between them, and so macro_vocabulary.py -- a candidate for a
# future standalone repo -- has a minimal, single-purpose dependency here
# rather than pulling in all of rdf_export.py's edge-table logic.
FXPCN = Namespace('https://fx-pcn.local/ontology#')
KG = Namespace('https://fx-pcn.local/kg/')
