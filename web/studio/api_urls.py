from django.urls import path

from .api import (
    DataUploadApi,
    DistributionAreasApi,
    PipelineRunApi,
    PipelineStagesApi,
    ProfilesApi,
    SimulationApi,
    SimulationOptionsApi,
    StageRunApi,
)

app_name = 'studio_api'

urlpatterns = [
    path('catalog/distribution-areas/', DistributionAreasApi.as_view(), name='distribution-areas'),
    path('catalog/profiles/', ProfilesApi.as_view(), name='profiles'),
    path('simulations/options/', SimulationOptionsApi.as_view(), name='simulation-options'),
    path('simulations/', SimulationApi.as_view(), name='simulations'),
    path('pipeline/stages/', PipelineStagesApi.as_view(), name='pipeline-stages'),
    path('pipeline/stages/<str:stage_id>/run/', StageRunApi.as_view(), name='pipeline-stage-run'),
    path('pipeline/runs/<uuid:run_id>/', PipelineRunApi.as_view(), name='pipeline-run'),
    path('data/uploads/<str:dataset>/', DataUploadApi.as_view(), name='data-upload'),
]
