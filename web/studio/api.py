from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from django.conf import settings
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import (
    ApiErrorSerializer,
    DataUploadResponseSerializer,
    PipelineRunSerializer,
    SimulationOptionsSerializer,
    SimulationRequestSerializer,
    SimulationResponseSerializer,
    StageRunRequestSerializer,
    StageSerializer,
)
from .models import PipelineRun
from .services.distribution import (
    distributor_info,
    geojson_payload,
    tariff_profiles_for_cnpj,
)
from .services.product import (
    DISPLAY_TIMEZONE,
    available_regions,
    effective_date_for,
    operational_status,
    replay_windows,
    simulate_customer,
    simulation_available,
)
from .services.runner import launch_stage
from .services.stage_registry import STAGE_MAP, stage_sections, stage_status
from motor_sin.common.io import read_table, write_table

ROOT = Path(settings.PREDICTA_PROJECT_ROOT)

# Canonical processed-data paths a frontend is allowed to overwrite directly via
# DataUploadApi. Kept separate from stage_registry outputs: those are pipeline-script
# outputs, this is the "push new data" side of the same artifacts (see AGENTS.md).
UPLOAD_DATASET_PATHS: dict[str, Path] = {
    'load': ROOT / 'data/processed/demand/load_hourly.parquet',
    'supply': ROOT / 'data/processed/generation/supply_by_subsystem_hourly.parquet',
    'tariffs': ROOT / 'data/processed/tariff/base_tariffs.parquet',
    'climate_e3': ROOT / 'data/processed/climate/zone_climate_hourly_e3.parquet',
    # Janelas de replay 24h: sem isto o modo `replay` de /simulations/ falha com
    # "Não há janela histórica completa de 24h". É o único artefato de outputs/ aqui.
    'predictions': ROOT / 'outputs/metrics/e3_real_pilot_predictions.parquet',
    'signal': ROOT / 'outputs/contracts/system_signal_v1.parquet',
}


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if pd.isna(value) if not isinstance(value, (str, bytes, bool, dict, list, tuple, set)) else False:
        return None
    return value


def _hourly_payload(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dict(orient='records'):
        item = _json_value(row)
        timestamp = pd.Timestamp(item['interval_start_utc']).tz_convert(DISPLAY_TIMEZONE)
        flags = item.get('quality_flags', [])
        if isinstance(flags, str):
            try:
                import json
                flags = json.loads(flags)
            except ValueError:
                flags = [flags]
        context = 'HOUR_MONTH'
        reference_n = None
        for flag in flags or []:
            flag = str(flag)
            if flag.startswith('DEMAND_PERCENTILE_CONTEXT_'):
                context = flag.replace('DEMAND_PERCENTILE_CONTEXT_', '')
            if flag.startswith('DEMAND_PERCENTILE_REFERENCE_N_'):
                try:
                    reference_n = int(flag.replace('DEMAND_PERCENTILE_REFERENCE_N_', ''))
                except ValueError:
                    pass
        base = float(item['base_total_rs_kwh'])
        dynamic = float(item['dynamic_tariff_rs_kwh'])
        rows.append({
            'interval_start_utc': item['interval_start_utc'],
            'local_iso': timestamp.isoformat(),
            'time': timestamp.strftime('%d/%m %Hh'),
            'base_rs_kwh': base,
            'dynamic_rs_kwh': dynamic,
            'consumption_kwh': float(item['consumption_kwh']),
            'optimized_consumption_kwh': float(item['optimized_consumption_kwh']),
            'multiplier': float(item['final_multiplier']),
            'demand_pressure': float(item['demand_pressure']),
            'demand_p50_mw': float(item['demand_p50_mw']),
            'demand_context': context,
            'demand_reference_n': reference_n,
            'delta_pct': 100 * (dynamic / base - 1) if base else 0,
        })
    return rows


class DistributionAreasApi(APIView):
    @extend_schema(
        tags=['Catálogo'],
        responses={200: OpenApiResponse(description='GeoJSON das áreas de concessão')},
    )
    def get(self, request):
        return Response(geojson_payload())


class ProfilesApi(APIView):
    @extend_schema(
        tags=['Catálogo'],
        parameters=[
            OpenApiParameter('cnpj', str, OpenApiParameter.QUERY, required=True),
            OpenApiParameter('region', str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter('mode', str, OpenApiParameter.QUERY, enum=['replay', 'operational'], required=False),
            OpenApiParameter('replay_issue', str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter('effective_date', str, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description='Distribuidora e perfis tarifários')},
    )
    def get(self, request):
        cnpj = request.query_params.get('cnpj', '')
        region = request.query_params.get('region') or None
        mode = request.query_params.get('mode', 'replay')
        replay_key = request.query_params.get('replay_issue') or None
        if mode not in {'replay', 'operational'}:
            return Response({'detail': 'mode deve ser replay ou operational.'}, status=status.HTTP_400_BAD_REQUEST)
        effective_raw = request.query_params.get('effective_date')
        effective = None
        if effective_raw:
            try:
                effective = date.fromisoformat(effective_raw)
            except ValueError:
                return Response({'detail': 'effective_date deve estar em YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        if effective is None and region:
            effective = effective_date_for(region, mode, replay_key)
        return Response({
            'distributor': _json_value(distributor_info(cnpj)),
            'profiles': _json_value(tariff_profiles_for_cnpj(cnpj, region, effective_date=effective)),
            'display_timezone': DISPLAY_TIMEZONE,
        })


class SimulationOptionsApi(APIView):
    @extend_schema(
        tags=['Simulação'],
        parameters=[
            OpenApiParameter('region', str, OpenApiParameter.QUERY, required=True),
            OpenApiParameter('mode', str, OpenApiParameter.QUERY, enum=['replay', 'operational']),
        ],
        responses={200: SimulationOptionsSerializer},
    )
    def get(self, request):
        region = request.query_params.get('region', '')
        mode = request.query_params.get('mode', 'replay')
        if mode not in {'replay', 'operational'}:
            return Response({'detail': 'mode deve ser replay ou operational.'}, status=status.HTTP_400_BAD_REQUEST)
        replay_key = request.query_params.get('replay_key') or None
        return Response({
            'region': region,
            'mode': mode,
            'effective_date': (effective_date_for(region, mode, replay_key).isoformat()
                               if effective_date_for(region, mode, replay_key) else None),
            'operational_status': operational_status(region),
            'replay_windows': replay_windows(region),
            'simulation_available': simulation_available(region, mode, replay_key),
            'display_timezone': DISPLAY_TIMEZONE,
            'regions': [{'id': key, 'available': value} for key, value in available_regions().items()],
        })


class SimulationApi(APIView):
    @extend_schema(
        tags=['Simulação'],
        request=SimulationRequestSerializer,
        responses={
            200: SimulationResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, description='Payload inválido ou simulação indisponível'),
        },
    )
    def post(self, request):
        serializer = SimulationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            result, frame = simulate_customer(
                region=payload['region'],
                cnpj=payload['cnpj'],
                distributor=payload['distributor'],
                profile=payload['profile'],
                monthly_kwh=payload['monthly_kwh'],
                customer_type=payload['customer_type'],
                mode=payload['mode'],
                replay_key=payload.get('replay_key') or None,
                flexible_fraction=payload['flexible_pct'] / 100,
            )
        except (ValueError, KeyError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = _json_value(result)
        response['hourly'] = _hourly_payload(frame)
        return Response(response)


def _param_dict(param) -> dict[str, Any]:
    return {
        'name': param.name,
        'label': param.label,
        'kind': param.kind,
        'default': param.default,
        'help': param.help,
        'choices': [list(pair) for pair in param.choices],
        'required': param.required,
    }


def _stage_dict(stage, status_info: dict[str, Any]) -> dict[str, Any]:
    return {
        'id': stage.id,
        'section': stage.section,
        'title': stage.title,
        'summary': stage.summary,
        'explanation': stage.explanation,
        'why': stage.why,
        'status': status_info['status'],
        'required': status_info['required'],
        'outputs': status_info['outputs'],
        'params': [_param_dict(p) for p in stage.params],
    }


def _run_dict(run: PipelineRun) -> dict[str, Any]:
    log_tail = ''
    if run.log_path and Path(run.log_path).exists():
        try:
            log_tail = Path(run.log_path).read_text(encoding='utf-8', errors='replace')[-20000:]
        except OSError:
            log_tail = ''
    return {
        'id': run.id,
        'stage_id': run.stage_id,
        'stage_label': run.stage_label,
        'status': run.status,
        'parameters': run.parameters,
        'return_code': run.return_code,
        'error_message': run.error_message,
        'created_at': run.created_at,
        'started_at': run.started_at,
        'finished_at': run.finished_at,
        'log_tail': log_tail,
    }


class PipelineStagesApi(APIView):
    """Lists every retraining/feature-engineering stage a frontend can trigger, with its
    editable params (e.g. experiment E1/E2/E3, algorithm, hyperparameters) and current
    readiness (READY/BLOCKED/DONE) so a UI can build dynamic forms. See AGENTS.md."""

    @extend_schema(
        tags=['Pipeline'],
        responses={200: StageSerializer(many=True)},
    )
    def get(self, request):
        stages = [
            _stage_dict(item['stage'], item)
            for section in stage_sections()
            for item in section['stages']
        ]
        return Response(stages)


class StageRunApi(APIView):
    """Triggers a pipeline stage (data sync, feature engineering, model validation/training,
    or the full retrain automation) asynchronously. Returns immediately with a run id to poll
    via PipelineRunApi. No auth in this MVP — see AGENTS.md for the security caveat."""

    @extend_schema(
        tags=['Pipeline'],
        request=StageRunRequestSerializer,
        responses={
            202: PipelineRunSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, description='Etapa desconhecida ou execução desabilitada'),
        },
    )
    def post(self, request, stage_id: str):
        if stage_id not in STAGE_MAP:
            return Response({'detail': f'Etapa desconhecida: {stage_id}'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = StageRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data.get('params') or {}
        try:
            run = launch_stage(stage_id, {k: str(v) for k, v in params.items()})
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_json_value(_run_dict(run)), status=status.HTTP_202_ACCEPTED)


class PipelineRunApi(APIView):
    """Polls the status/log of a run started via StageRunApi (or the /pipeline/ web UI)."""

    @extend_schema(tags=['Pipeline'], responses={200: PipelineRunSerializer})
    def get(self, request, run_id):
        run = get_object_or_404(PipelineRun, pk=run_id)
        return Response(_json_value(_run_dict(run)))


class DataUploadApi(APIView):
    """Lets an external frontend push a new CSV/Parquet straight into one of the canonical
    processed-data files that the simulation and training scripts read (load, supply, tariffs,
    climate_e3). This is the "send new data" half of retraining; trigger `validate_model` /
    `train_model` / `full_automation` via StageRunApi afterwards to actually retrain on it.
    No schema validation beyond parseability — MVP, see AGENTS.md."""

    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=['Dados'],
        request={'multipart/form-data': {'type': 'object', 'properties': {'file': {'type': 'string', 'format': 'binary'}}}},
        responses={
            200: DataUploadResponseSerializer,
            400: OpenApiResponse(response=ApiErrorSerializer, description='dataset inválido ou arquivo ilegível'),
        },
    )
    def post(self, request, dataset: str):
        target = UPLOAD_DATASET_PATHS.get(dataset)
        if target is None:
            return Response(
                {'detail': f'dataset deve ser um de: {sorted(UPLOAD_DATASET_PATHS)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'Envie o arquivo no campo "file" (multipart/form-data).'}, status=status.HTTP_400_BAD_REQUEST)
        suffix = Path(upload.name).suffix.lower() or '.csv'
        tmp_path = target.with_suffix(f'.incoming{suffix}')
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, 'wb') as fh:
            for chunk in upload.chunks():
                fh.write(chunk)
        try:
            frame = read_table(tmp_path)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            return Response({'detail': f'Não foi possível ler o arquivo: {exc}'}, status=status.HTTP_400_BAD_REQUEST)
        write_table(frame, target)
        tmp_path.unlink(missing_ok=True)
        return Response({
            'dataset': dataset,
            'path': str(target.relative_to(ROOT)),
            'rows': len(frame),
            'columns': list(frame.columns),
        })
