from rest_framework import serializers


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)


class AnalyzeRequestSerializer(serializers.Serializer):
    origin = CoordinateSerializer()
    destination = CoordinateSerializer()
    vector = serializers.ChoiceField(choices=["departure", "arrival"])
    start_hour = serializers.IntegerField(min_value=0, max_value=23)
    end_hour = serializers.IntegerField(min_value=0, max_value=23)
    interval_minutes = serializers.ChoiceField(choices=[5, 10, 15, 30])
    days = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        min_length=1, max_length=7,
    )
    timezone = serializers.CharField(default="UTC")

    def validate(self, data):
        if data["end_hour"] < data["start_hour"]:
            raise serializers.ValidationError("end_hour must be >= start_hour.")
        if len(set(data["days"])) != len(data["days"]):
            raise serializers.ValidationError("days contains duplicates.")
        return data


class GeocodeRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=500)
    region = serializers.CharField(required=False, allow_blank=True, max_length=8, default="")


class SetupRequestSerializer(serializers.Serializer):
    api_key = serializers.CharField(max_length=200)
