from rest_framework import serializers


class SimulationRequestSerializer(serializers.Serializer):
    cnpj = serializers.CharField(max_length=20)
    region = serializers.CharField(max_length=10)
    distributor = serializers.CharField(max_length=120)
    profile = serializers.CharField(max_length=120)
    monthly_kwh = serializers.FloatField(min_value=1)
    customer_type = serializers.ChoiceField(
        choices=('residential', 'commercial', 'industrial_flat'),
        default='residential',
    )
    mode = serializers.ChoiceField(choices=('replay', 'operational'), default='replay')
    replay_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    flexible_pct = serializers.FloatField(min_value=0, max_value=80, default=20)


class SimulationResponseSerializer(serializers.Serializer):
    customer = serializers.DictField()
    concession = serializers.DictField(allow_null=True)
    optimization = serializers.DictField()
    window = serializers.DictField()
    hourly = serializers.ListField(child=serializers.DictField())
    simulation_mode = serializers.CharField()
    display_timezone = serializers.CharField()
    simulation_scope_pt = serializers.CharField()
    reference_tariff_mean_rs_kwh = serializers.FloatField()
    dynamic_tariff_mean_rs_kwh = serializers.FloatField()
    reference_cost_24h_rs = serializers.FloatField()
    dynamic_cost_24h_rs = serializers.FloatField()
    difference_pct = serializers.FloatField()


class ApiErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SimulationOptionsSerializer(serializers.Serializer):
    region = serializers.CharField()
    mode = serializers.CharField()
    effective_date = serializers.CharField(allow_null=True)
    operational_status = serializers.DictField()
    replay_windows = serializers.ListField(child=serializers.DictField())
    simulation_available = serializers.BooleanField()
    display_timezone = serializers.CharField()


class StageParamSerializer(serializers.Serializer):
    name = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.CharField()
    default = serializers.CharField(allow_blank=True)
    help = serializers.CharField(allow_blank=True)
    choices = serializers.ListField(child=serializers.ListField(child=serializers.CharField()))
    required = serializers.BooleanField()


class StageSerializer(serializers.Serializer):
    id = serializers.CharField()
    section = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField()
    explanation = serializers.CharField()
    why = serializers.CharField()
    status = serializers.CharField()
    required = serializers.ListField(child=serializers.DictField())
    outputs = serializers.ListField(child=serializers.DictField())
    params = StageParamSerializer(many=True)


class StageRunRequestSerializer(serializers.Serializer):
    """Body is a free-form map of {param_name: value}; every Stage.params entry is optional
    and falls back to its registry default when omitted, so this stays a passthrough DictField
    instead of a fixed schema (each stage has a different param set)."""
    params = serializers.DictField(required=False, default=dict)


class PipelineRunSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    stage_id = serializers.CharField()
    stage_label = serializers.CharField()
    status = serializers.CharField()
    parameters = serializers.DictField()
    return_code = serializers.IntegerField(allow_null=True)
    error_message = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    log_tail = serializers.CharField(allow_blank=True)


class DataUploadResponseSerializer(serializers.Serializer):
    dataset = serializers.CharField()
    path = serializers.CharField()
    rows = serializers.IntegerField()
    columns = serializers.ListField(child=serializers.CharField())
