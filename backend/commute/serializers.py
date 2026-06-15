from rest_framework import serializers

from commute.coords import round_coord
from commute.models import SavedAddress, SavedRoute


class CoordinateSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)

    def validate(self, data):
        # Round on the way in so cache lookups and stored rows use a consistent
        # precision regardless of how precise the geocoder was (issue #1).
        data["lat"] = round_coord(data["lat"])
        data["lng"] = round_coord(data["lng"])
        return data


class AnalyzeRequestSerializer(serializers.Serializer):
    origin = CoordinateSerializer()
    destination = CoordinateSerializer()
    vector = serializers.ChoiceField(choices=["departure", "arrival"])
    start_hour = serializers.IntegerField(min_value=0, max_value=23)
    end_hour = serializers.IntegerField(min_value=0, max_value=23)
    # Structural choices only; which of these a tier may actually use is
    # enforced against commute.tiers in the analyze view. 10 was dropped (#15);
    # 60 added and 5 is "coming soon" (#32).
    interval_minutes = serializers.ChoiceField(choices=[5, 15, 30, 60])
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


class RouteRequestSerializer(serializers.Serializer):
    origin = CoordinateSerializer()
    destination = CoordinateSerializer()


class GeocodeRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=500)
    region = serializers.CharField(required=False, allow_blank=True, max_length=8, default="")


class SetupRequestSerializer(serializers.Serializer):
    api_key = serializers.CharField(max_length=200)


class GoogleAuthSerializer(serializers.Serializer):
    credential = serializers.CharField()


class SavedAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedAddress
        fields = ["id", "label", "address", "lat", "lng", "created_at"]
        read_only_fields = ["id", "created_at"]


class SavedRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedRoute
        fields = [
            "id", "name", "origin_label", "origin_lat", "origin_lng",
            "dest_label", "dest_lat", "dest_lng", "params",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
