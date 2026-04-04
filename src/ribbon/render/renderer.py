from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from ribbon.models import BusDepartureItem, MarketDirection, MarketIndexItem, ModeName, RibbonSnapshot
from ribbon.render.typography import icon_glyph, load_font
from ribbon.settings import SETTINGS


WHITE = 255
BLACK = 0
SURFACE = 244
TEXT_MUTED = 76
TEXT_SOFT = 118
RULE = 168
HEAVY_RULE = 60
LOCAL_TZ = ZoneInfo(SETTINGS.timezone)
DEGREE = "\N{DEGREE SIGN}"


class RibbonRenderer:
    def __init__(self, center_weekend_stop_names: bool = True) -> None:
        self.center_weekend_stop_names = center_weekend_stop_names

    def render_to_path(self, snapshot: RibbonSnapshot, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.render(snapshot).save(path, format="PNG")
        return path

    def render(self, snapshot: RibbonSnapshot) -> Image.Image:
        image = Image.new("L", (SETTINGS.width, SETTINGS.height), color=WHITE)
        draw = ImageDraw.Draw(image)

        if snapshot.mode == ModeName.WEEKDAY_COMMUTE_NOW:
            self._render_weekday_commute_now(draw, snapshot)
        elif snapshot.mode == ModeName.WEEKEND_MULTI_STOP:
            self._render_weekend_multi_stop(draw, snapshot)
        else:
            self._render_ambient_info(draw, snapshot)
        return image

    def _render_weekday_commute_now(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot) -> None:
        left_w = 250
        center_w = 760
        right_w = SETTINGS.width - left_w - center_w
        right_x = left_w + center_w

        draw.rectangle((0, 0, SETTINGS.width, SETTINGS.height), fill=WHITE)
        draw.line((left_w, 0, left_w, SETTINGS.height), fill=BLACK, width=2)
        draw.line((right_x, 0, right_x, SETTINGS.height), fill=BLACK, width=2)

        self._draw_weekday_left_rail(draw, snapshot, 0, left_w)
        self._draw_weekday_center(draw, snapshot, left_w, center_w)
        self._draw_weekday_news_rail(draw, snapshot, right_x, right_w)

    def _render_weekend_multi_stop(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot) -> None:
        footer_h = 40
        content_h = SETTINGS.height - footer_h
        column_w = SETTINGS.width // 4
        header_h = 72
        row_h = (content_h - header_h) // 4
        divider_w = 4

        draw.rectangle((0, 0, SETTINGS.width, SETTINGS.height), fill=WHITE)
        stops = list(snapshot.multi_stop.stops) if snapshot.multi_stop else []

        for index in range(4):
            x0 = index * column_w
            x1 = x0 + column_w
            stop = stops[index] if index < len(stops) else None
            inner_right = x1 - (divider_w if index < 3 else 0)

            draw.rectangle((x0, 0, inner_right, header_h), fill=BLACK)
            if index < 3:
                draw.rectangle((inner_right, 0, x1, content_h), fill=BLACK)

            stop_title_font = self._font_space(28, 700)
            stop_id_font = self._font_inter(12, 700)
            stop_title = self._ellipsize(
                draw,
                (stop.stop_title if stop else "Unavailable").upper(),
                stop_title_font,
                inner_right - x0 - 28,
            )
            title_w = self._text_width(draw, stop_title, stop_title_font)
            if self.center_weekend_stop_names:
                title_x = x0 + max(14, ((inner_right - x0) - title_w) // 2)
            else:
                title_x = x0 + 14
            self._draw_text(draw, title_x, 16, stop_title, stop_title_font, WHITE)

            stop_id_text = f"STOP ID: {stop.stop_id if stop else '--'}"
            stop_id_w = self._text_width(draw, stop_id_text, stop_id_font)
            self._draw_text(draw, inner_right - 14 - stop_id_w, header_h - 18, stop_id_text, stop_id_font, WHITE)

            departures = stop.departures[:4] if stop else []
            for row_index in range(4):
                row_top = header_h + row_index * row_h
                row_bottom = row_top + row_h
                if row_index < 3:
                    draw.line((x0, row_bottom, inner_right, row_bottom), fill=BLACK, width=2)
                self._draw_weekend_row(
                    draw,
                    departures[row_index] if row_index < len(departures) else None,
                    x0,
                    row_top,
                    inner_right,
                    row_bottom,
                )

        self._draw_weekend_footer(draw, snapshot, content_h, footer_h)

    def _render_ambient_info(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot) -> None:
        left_w = 340
        divider_w = 4
        draw.rectangle((0, 0, SETTINGS.width, SETTINGS.height), fill=WHITE)
        draw.rectangle((0, 0, SETTINGS.width - 1, SETTINGS.height - 1), outline=BLACK, width=divider_w)
        draw.rectangle((left_w - divider_w, 0, left_w, SETTINGS.height), fill=BLACK)

        self._draw_ambient_left_rail(draw, snapshot, 0, left_w)
        self._draw_ambient_main(draw, snapshot, left_w, SETTINGS.width - left_w)

    def _draw_weekday_left_rail(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot, x0: int, width: int) -> None:
        pad = 18
        left = x0 + pad
        right = x0 + width - pad
        now = snapshot.generated_at.astimezone(LOCAL_TZ)
        weather = snapshot.weather

        clock_font = self._font_space(82, 700)
        date_font = self._font_space(25, 700)
        meta_font = self._font_inter(12, 700)
        temp_font = self._font_space(42, 700)
        detail_font = self._font_inter(15, 700)
        metric_label_font = self._font_inter(11, 700)
        metric_value_font = self._font_space(15, 700)
        solar_font = self._font_inter(12, 700)
        market_label_font = self._font_inter(10, 700)
        market_value_font = self._font_space(14, 700)

        clock_y = 14
        self._draw_text(draw, left, clock_y, now.strftime("%H:%M"), clock_font, BLACK)
        date_y = clock_y + self._text_height(draw, "22:02", clock_font) + 44
        self._draw_text(draw, left, date_y, now.strftime("%a %d %b").upper(), date_font, BLACK)

        meta_top = date_y + self._text_height(draw, "SAT 04 APR", date_font) + 16
        self._draw_icon_text_row(draw, left, meta_top, "location_on", 16, weather.location_label.upper(), meta_font, BLACK)
        self._draw_icon_text_row(draw, left, meta_top + 20, "schedule", 16, f"UPDATED {now.strftime('%H:%M')}", meta_font, BLACK)

        weather_y = meta_top + 52
        self._draw_icon(draw, left, weather_y - 4, self._condition_icon_name(weather.condition_label), 34)
        self._draw_text(draw, left + 44, weather_y - 10, self._format_temperature(weather.temperature_c), temp_font, BLACK)

        high_low = self._format_high_low(weather)
        detail_x = left + 44
        detail_max_width = right - detail_x
        detail_line, detail_subline = self._fit_weather_detail_lines(
            draw,
            weather.condition_label.upper(),
            high_low,
            detail_font,
            self._font_inter(13, 700),
            detail_max_width,
        )
        detail_y = weather_y + 40
        self._draw_text(draw, detail_x, detail_y, detail_line, detail_font, TEXT_MUTED)
        detail_bottom = detail_y + self._text_height(draw, detail_line, detail_font)
        if detail_subline:
            detail_subline_font = self._font_inter(13, 700)
            detail_subline_y = detail_bottom + 4
            self._draw_text(draw, detail_x, detail_subline_y, detail_subline, detail_subline_font, TEXT_MUTED)
            detail_bottom = detail_subline_y + self._text_height(draw, detail_subline, detail_subline_font)

        divider_y = detail_bottom + 16
        draw.line((left, divider_y, right, divider_y), fill=RULE, width=1)

        metrics_top = divider_y + 14
        humidity_top = metrics_top
        aqi_top = metrics_top + 24
        self._draw_icon_metric_row(
            draw,
            left,
            humidity_top,
            width - (pad * 2),
            "humidity_percentage",
            "Humidity",
            self._format_percent(weather.humidity_pct),
            metric_label_font,
            metric_value_font,
        )
        self._draw_icon_metric_row(
            draw,
            left,
            aqi_top,
            width - (pad * 2),
            "air",
            "AQI",
            self._format_aqi(weather.aqi_index, weather.aqi_label),
            metric_label_font,
            metric_value_font,
        )

        metrics_bottom = aqi_top + max(
            self._text_height(draw, "AQI", metric_label_font),
            self._text_height(draw, "99 MODERATE", metric_value_font),
        )
        solar_font_h = self._text_height(draw, "SUNRISE 06:10", solar_font)
        solar_top, market_divider_y, market_top = self._fit_solar_market_sections(
            metrics_bottom=metrics_bottom,
            solar_block_height=solar_font_h + 22,
            market_section_height=52,
            bottom_margin=18,
            minimum_gap_after_metrics=14,
            minimum_gap_before_market=14,
        )
        self._draw_icon_text_row(draw, left, solar_top, "wb_sunny", 16, f"SUNRISE {self._format_clock(weather.sunrise_local)}", solar_font, BLACK)
        self._draw_icon_text_row(draw, left, solar_top + 22, "bedtime", 16, f"SUNSET {self._format_clock(weather.sunset_local)}", solar_font, BLACK)

        draw.line((left, market_divider_y, right, market_divider_y), fill=RULE, width=1)
        self._draw_market_stack(draw, snapshot, "NIFTY", left, market_top + 2, width - (pad * 2), market_label_font, market_value_font)
        self._draw_market_stack(draw, snapshot, "S&P 500", left, market_top + 32, width - (pad * 2), market_label_font, market_value_font)

    def _draw_weekday_news_rail(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot, x0: int, width: int) -> None:
        pad = 18
        left = x0 + pad
        usable_w = width - (pad * 2)
        top = 18
        title_font = self._font_space(32, 700)
        meta_font = self._font_space(12, 700)
        time_font = self._font_inter(12, 700)
        headline_font = self._font_space(18, 700)

        self._draw_text(draw, left, top, "NEWS", title_font, BLACK)
        divider_y = top + self._text_height(draw, "NEWS", title_font) + 22
        draw.line((left, divider_y, left + usable_w, divider_y), fill=HEAVY_RULE, width=2)

        stories_top = divider_y + 18
        available_h = SETTINGS.height - stories_top - 18
        headlines = self._headline_subset_to_fit(
            draw,
            snapshot.headlines,
            usable_w,
            available_h,
            meta_font,
            headline_font,
            max_lines=3,
            counts=(6, 5),
        )
        self._draw_headline_stack(
            draw,
            headlines,
            left,
            stories_top,
            usable_w,
            meta_font,
            time_font,
            headline_font,
            divider_gap=10,
            max_lines=3,
        )

    def _draw_weekday_center(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot, x0: int, width: int) -> None:
        stop = snapshot.primary_stop
        left = x0 + 32
        right = x0 + width - 32
        title_font = self._font_space(34, 700)
        label_font = self._font_inter(11, 700)

        stop_id = stop.stop_id if stop else SETTINGS.weekday_commute_stop.stop_id
        stop_title = stop.stop_title if stop else SETTINGS.weekday_commute_stop.title
        title = f"STOP {stop_id} / {stop_title}".upper()
        self._draw_text(
            draw,
            left,
            38,
            self._ellipsize(draw, title, title_font, width - 64),
            title_font,
            BLACK,
        )

        hero_top = 96
        hero_bottom = 226
        draw.rectangle((left, hero_top, right, hero_bottom), fill=SURFACE)
        draw.line((left, hero_bottom, right, hero_bottom), fill=BLACK, width=4)

        if stop and stop.hero:
            hero = stop.hero
            route_x = left + 24
            dest_x = left + 170
            due_x = right - 152

            self._draw_text(draw, route_x, hero_top + 14, "ROUTE", label_font, TEXT_MUTED)
            self._draw_text(draw, route_x, hero_top + 34, hero.route_number, self._font_space(74, 700), BLACK)

            self._draw_text(draw, dest_x, hero_top + 14, "DESTINATION", label_font, TEXT_MUTED)
            hero_destination_lines, hero_destination_font = self._fit_hero_destination(
                draw,
                hero.destination.upper(),
                max_width=max(120, due_x - dest_x - 24),
                max_height=42,
            )
            self._draw_lines(
                draw,
                dest_x,
                hero_top + 38,
                hero_destination_lines,
                hero_destination_font,
                BLACK,
                0,
            )

            scheduled_text = f"Scheduled {hero.scheduled_label or '--:--'}"
            if hero.irregularity_flag:
                scheduled_text = f"{scheduled_text} / {hero.irregularity_flag}"
            self._draw_icon(draw, dest_x, hero_top + 84, "schedule", 18)
            self._draw_text(
                draw,
                dest_x + 24,
                hero_top + 86,
                self._ellipsize(draw, scheduled_text, self._font_space(18, 500), max(140, due_x - dest_x - 24)),
                self._font_space(18, 500),
                BLACK,
            )

            self._draw_text(draw, due_x, hero_top + 14, "DUE IN", label_font, TEXT_MUTED)
            due_number, due_unit = self._split_due_label(hero.due_label)
            self._draw_text(draw, due_x, hero_top + 28, due_number, self._font_space(76, 700), BLACK)
            if due_unit:
                self._draw_text(draw, due_x + 10, hero_top + 104, due_unit, self._font_space(24, 700), BLACK)
        else:
            self._draw_text(draw, left + 24, hero_top + 52, "NO LIVE BOARD AVAILABLE", self._font_space(30, 700), BLACK)

        row_top = hero_bottom + 16
        row_height = 68
        departures = stop.departures[1:4] if stop else []
        for index, departure in enumerate(departures):
            y = row_top + index * row_height
            if index:
                draw.line((left, y, right, y), fill=RULE, width=1)
            self._draw_weekday_departure_row(draw, departure, left, y + 14, right)

        if snapshot.degraded_reason:
            self._draw_text(
                draw,
                left,
                SETTINGS.height - 26,
                self._ellipsize(draw, snapshot.degraded_reason.upper(), self._font_inter(10, 700), width - 64),
                self._font_inter(10, 700),
                TEXT_MUTED,
            )

    def _draw_weekday_departure_row(self, draw: ImageDraw.ImageDraw, departure: BusDepartureItem, left: int, y: int, right: int) -> None:
        route_font = self._font_space(28, 700)
        destination_font = self._font_space(20, 700)
        time_font = self._font_space(20, 500)
        due_font = self._font_space(20, 700)
        marker_font = self._font_inter(10, 700)

        route_x = left
        destination_x = left + 72
        time_text = self._format_departure_time(departure)
        due_text = f"({self._format_due_minutes(departure.due_minutes)})"
        due_anchor_right, time_anchor_right, destination_right = self._weekday_row_slots(draw, right, time_font, due_font)
        due_w = self._text_width(draw, due_text, due_font)
        time_w = self._text_width(draw, time_text, time_font)
        due_x = due_anchor_right - due_w
        time_x = time_anchor_right - time_w
        destination_w = max(140, destination_right - destination_x)

        self._draw_text(draw, route_x, y, departure.route_number, route_font, BLACK)
        self._draw_text(
            draw,
            destination_x,
            y + 2,
            self._ellipsize(draw, departure.destination.upper(), destination_font, destination_w),
            destination_font,
            BLACK,
        )
        self._draw_text(draw, time_x, y + 2, time_text, time_font, BLACK)
        self._draw_text(draw, due_x, y + 2, due_text, due_font, BLACK)

        if departure.marker:
            self._draw_text(
                draw,
                destination_x,
                y + 28,
                self._ellipsize(draw, departure.marker.upper(), marker_font, destination_w),
                marker_font,
                TEXT_MUTED,
            )

    def _draw_weekend_row(
        self,
        draw: ImageDraw.ImageDraw,
        departure: BusDepartureItem | None,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> None:
        pad = 16
        route_font = self._font_space(46, 700)
        due_font = self._font_space(28, 700)
        destination_font = self._font_space(17, 700)
        time_font = self._font_inter(18, 700)

        if departure is None:
            self._draw_text(draw, x0 + pad, y0 + 26, "--", route_font, TEXT_SOFT)
            self._draw_text(draw, x0 + pad, y0 + 64, "NO LATER SERVICE", destination_font, TEXT_MUTED)
            return

        due_text = self._uppercase_due(departure.due_minutes)
        due_w = self._text_width(draw, due_text, due_font)
        self._draw_text(draw, x0 + pad, y0 + 10, departure.route_number, route_font, BLACK)
        self._draw_text(draw, x1 - pad - due_w, y0 + 20, due_text, due_font, BLACK)

        time_text = self._format_departure_time(departure)
        time_w = self._text_width(draw, time_text, time_font)
        destination_w = x1 - x0 - (pad * 2) - time_w - 24
        self._draw_text(
            draw,
            x0 + pad,
            y0 + 60,
            self._ellipsize(draw, departure.destination.upper(), destination_font, destination_w),
            destination_font,
            BLACK,
        )
        self._draw_text(draw, x1 - pad - time_w, y0 + 61, time_text, time_font, TEXT_MUTED)

    def _draw_weekend_footer(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot, footer_top: int, footer_h: int) -> None:
        now = snapshot.generated_at.astimezone(LOCAL_TZ)
        weather = snapshot.weather
        draw.rectangle((0, footer_top, SETTINGS.width, footer_top + footer_h), fill=BLACK)

        time_font = self._font_space(24, 700)
        date_font = self._font_space(21, 700)
        temp_font = self._font_space(23, 700)

        self._draw_text(draw, 16, footer_top + 6, now.strftime("%H:%M"), time_font, WHITE)
        date_text = now.strftime("%a %d %b").upper()
        date_w = self._text_width(draw, date_text, date_font)
        self._draw_text(draw, (SETTINGS.width - date_w) // 2, footer_top + 7, date_text, date_font, WHITE)

        temp_text = self._format_temperature(weather.temperature_c)
        temp_w = self._text_width(draw, temp_text, temp_font)
        icon_x = SETTINGS.width - 16 - temp_w - 28
        self._draw_icon(draw, icon_x, footer_top + 7, self._condition_icon_name(weather.condition_label), 22, fill=WHITE, axis_fill=1)
        self._draw_text(draw, SETTINGS.width - 16 - temp_w, footer_top + 6, temp_text, temp_font, WHITE)

    def _draw_ambient_left_rail(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot, x0: int, width: int) -> None:
        pad = 28
        left = x0 + pad
        right = x0 + width - pad
        now = snapshot.generated_at.astimezone(LOCAL_TZ)
        weather = snapshot.weather

        clock_font = self._font_space(90, 700)
        date_font = self._font_space(28, 700)
        meta_font = self._font_inter(13, 700)
        temp_font = self._font_space(46, 700)
        detail_font = self._font_inter(17, 700)
        metric_label_font = self._font_inter(11, 700)
        metric_value_font = self._font_space(18, 700)
        solar_font = self._font_inter(14, 700)
        market_label_font = self._font_inter(11, 700)
        market_value_font = self._font_space(17, 700)

        clock_y = 16
        self._draw_text(draw, left, clock_y, now.strftime("%H:%M"), clock_font, BLACK)
        date_y = clock_y + self._text_height(draw, "22:02", clock_font) + 40
        self._draw_text(draw, left, date_y, now.strftime("%a %d %b").upper(), date_font, BLACK)

        meta_top = date_y + self._text_height(draw, "SAT 04 APR", date_font) + 16
        self._draw_icon_text_row(draw, left, meta_top, "location_on", 18, weather.location_label.upper(), meta_font, BLACK)
        self._draw_icon_text_row(draw, left, meta_top + 22, "schedule", 18, f"UPDATED {now.strftime('%H:%M')}", meta_font, BLACK)

        weather_y = meta_top + 52
        self._draw_icon(draw, left, weather_y - 2, self._condition_icon_name(weather.condition_label), 40)
        self._draw_text(draw, left + 52, weather_y - 10, self._format_temperature(weather.temperature_c), temp_font, BLACK)

        high_low = self._format_high_low(weather)
        detail_x = left + 54
        detail_max_width = right - detail_x
        detail_line, detail_subline = self._fit_weather_detail_lines(
            draw,
            weather.condition_label.upper(),
            high_low,
            detail_font,
            self._font_inter(15, 700),
            detail_max_width,
        )
        detail_y = weather_y + 42
        self._draw_text(draw, detail_x, detail_y, detail_line, detail_font, TEXT_MUTED)
        detail_bottom = detail_y + self._text_height(draw, detail_line, detail_font)
        if detail_subline:
            detail_subline_font = self._font_inter(15, 700)
            detail_subline_y = detail_bottom + 4
            self._draw_text(draw, detail_x, detail_subline_y, detail_subline, detail_subline_font, TEXT_MUTED)
            detail_bottom = detail_subline_y + self._text_height(draw, detail_subline, detail_subline_font)

        divider_y = detail_bottom + 16
        draw.line((left, divider_y, right, divider_y), fill=RULE, width=1)

        metrics_top = divider_y + 14
        humidity_top = metrics_top
        aqi_top = metrics_top + 26
        self._draw_icon_metric_row(
            draw,
            left,
            humidity_top,
            width - (pad * 2),
            "humidity_percentage",
            "Humidity",
            self._format_percent(weather.humidity_pct),
            metric_label_font,
            metric_value_font,
        )
        self._draw_icon_metric_row(
            draw,
            left,
            aqi_top,
            width - (pad * 2),
            "air",
            "AQI",
            self._format_aqi(weather.aqi_index, weather.aqi_label),
            metric_label_font,
            metric_value_font,
        )

        metrics_bottom = aqi_top + max(
            self._text_height(draw, "AQI", metric_label_font),
            self._text_height(draw, "99 MODERATE", metric_value_font),
        )
        solar_font_h = self._text_height(draw, "SUNRISE 06:10", solar_font)
        solar_top, market_divider_y, market_top = self._fit_solar_market_sections(
            metrics_bottom=metrics_bottom,
            solar_block_height=solar_font_h + 26,
            market_section_height=58,
            bottom_margin=18,
            minimum_gap_after_metrics=16,
            minimum_gap_before_market=14,
        )
        self._draw_icon_text_row(draw, left, solar_top, "wb_sunny", 18, f"SUNRISE {self._format_clock(weather.sunrise_local)}", solar_font, BLACK)
        self._draw_icon_text_row(draw, left, solar_top + 26, "bedtime", 18, f"SUNSET {self._format_clock(weather.sunset_local)}", solar_font, BLACK)

        draw.line((left, market_divider_y, right, market_divider_y), fill=RULE, width=1)
        self._draw_market_stack(draw, snapshot, "NIFTY", left, market_top + 2, width - (pad * 2), market_label_font, market_value_font)
        self._draw_market_stack(draw, snapshot, "S&P 500", left, market_top + 32, width - (pad * 2), market_label_font, market_value_font)

    def _draw_ambient_main(self, draw: ImageDraw.ImageDraw, snapshot: RibbonSnapshot, x0: int, width: int) -> None:
        pad_x = 34
        left = x0 + pad_x
        usable_w = width - (pad_x * 2)
        top = 18

        title_font = self._font_space(36, 700)
        updated_font = self._font_inter(12, 700)
        meta_font = self._font_space(13, 700)
        time_font = self._font_inter(12, 700)
        headline_font = self._font_space(24, 700)

        self._draw_text(draw, left, top, "HEADLINES", title_font, BLACK)
        updated_text = f"LAST UPDATED {snapshot.generated_at.astimezone(LOCAL_TZ).strftime('%H:%M')}"
        updated_w = self._text_width(draw, updated_text, updated_font)
        self._draw_text(draw, left + usable_w - updated_w, top + 12, updated_text, updated_font, TEXT_MUTED)
        divider_y = top + self._text_height(draw, "HEADLINES", title_font) + 24
        draw.line((left, divider_y, left + usable_w, divider_y), fill=HEAVY_RULE, width=2)

        stories_top = divider_y + 18
        available_h = SETTINGS.height - stories_top - 18
        headlines = self._headline_subset_to_fit(
            draw,
            snapshot.headlines,
            usable_w,
            available_h,
            meta_font,
            headline_font,
            max_lines=2,
            counts=(6, 5),
        )
        self._draw_headline_stack(
            draw,
            headlines,
            left,
            stories_top,
            usable_w,
            meta_font,
            time_font,
            headline_font,
            divider_gap=12,
            max_lines=2,
        )

    def _draw_headline_stack(
        self,
        draw: ImageDraw.ImageDraw,
        headlines: Sequence,
        left: int,
        top: int,
        usable_w: int,
        meta_font,
        time_font,
        headline_font,
        divider_gap: int,
        max_lines: int,
    ) -> None:
        current_y = top
        meta_h = self._text_height(draw, "REUTERS", meta_font)
        headline_h = self._text_height(draw, "Ag", headline_font)

        for index, headline in enumerate(headlines):
            source_text = headline.source_name.upper()
            published_text = headline.published_at.astimezone(LOCAL_TZ).strftime("%H:%M") if headline.published_at else "--:--"
            self._draw_text(draw, left, current_y, source_text, meta_font, TEXT_MUTED)
            time_w = self._text_width(draw, published_text, time_font)
            self._draw_text(draw, left + usable_w - time_w, current_y + 1, published_text, time_font, TEXT_MUTED)

            lines = self._clamp_lines(draw, headline.title, headline_font, usable_w, max_lines)
            self._draw_lines(draw, left, current_y + meta_h + 8, lines, headline_font, BLACK, 2)

            current_y += meta_h + 8 + (len(lines) * headline_h) + (max(0, len(lines) - 1) * 2) + 14
            if index < len(headlines) - 1:
                draw.line((left, current_y, left + usable_w, current_y), fill=RULE, width=1)
                current_y += divider_gap

    def _draw_market_stack(
        self,
        draw: ImageDraw.ImageDraw,
        snapshot: RibbonSnapshot,
        market_key: str,
        left: int,
        top: int,
        usable_w: int,
        label_font,
        value_font,
    ) -> None:
        market = next(
            (
                item
                for item in snapshot.market_indices
                if item.code.upper() == market_key.upper() or item.label.upper() == market_key.upper()
            ),
            None,
        )

        self._draw_text(draw, left, top, market_key.upper(), label_font, TEXT_MUTED)
        if market is None:
            self._draw_text(draw, left, top + 12, "UNAVAILABLE", value_font, TEXT_SOFT)
            return

        market_text = self._format_market_line(market)
        value_y = top + 12
        icon_name = self._market_direction_icon_name(market.direction)
        icon_size = 16
        self._draw_icon(draw, left, value_y - 2, icon_name, icon_size)
        text_x = left + icon_size + 4
        available = max(40, usable_w - (icon_size + 4))
        self._draw_text(
            draw,
            text_x,
            value_y,
            self._ellipsize(draw, market_text, value_font, available),
            value_font,
            BLACK,
        )

    def _draw_icon_metric_row(
        self,
        draw: ImageDraw.ImageDraw,
        left: int,
        top: int,
        usable_w: int,
        icon_name: str,
        label: str,
        value: str,
        label_font,
        value_font,
    ) -> None:
        self._draw_icon(draw, left, top - 2, icon_name, 16)
        self._draw_text(draw, left + 24, top, label.upper(), label_font, TEXT_MUTED)
        value_w = self._text_width(draw, value, value_font)
        self._draw_text(draw, left + usable_w - value_w, top - 2, value, value_font, BLACK)

    def _draw_icon_text_row(
        self,
        draw: ImageDraw.ImageDraw,
        left: int,
        top: int,
        icon_name: str,
        size: int,
        text: str,
        font,
        fill: int,
    ) -> None:
        self._draw_icon(draw, left, top - 2, icon_name, size)
        self._draw_text(draw, left + size + 6, top, text, font, fill)

    def _draw_icon(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        name: str,
        size: int,
        *,
        fill: int = BLACK,
        axis_fill: int = 0,
    ) -> None:
        glyph = icon_glyph(name)
        draw.text(
            (x, y),
            glyph,
            font=self._font_symbols(size=size, fill=axis_fill),
            fill=fill,
        )

    def _market_direction_icon_name(self, direction: MarketDirection) -> str:
        if direction == MarketDirection.UP:
            return "arrow_drop_up"
        if direction == MarketDirection.DOWN:
            return "arrow_drop_down"
        return "trending_flat"

    def _condition_icon_name(self, condition_label: str) -> str:
        label = (condition_label or "").lower()
        if "rain" in label or "drizzle" in label:
            return "rainy"
        if "storm" in label or "thunder" in label:
            return "thunderstorm"
        if "cloud" in label or "overcast" in label:
            return "cloud"
        if "fog" in label or "mist" in label or "haze" in label:
            return "foggy"
        if "clear" in label or "sun" in label:
            return "wb_sunny"
        return "partly_cloudy_day"

    def _draw_text(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill: int) -> None:
        draw.text((x, y), text, font=font, fill=fill)

    def _draw_lines(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        lines: Sequence[str],
        font,
        fill: int,
        line_gap: int = 0,
    ) -> None:
        line_h = self._text_height(draw, "Ag", font)
        for index, line in enumerate(lines):
            self._draw_text(draw, x, y + index * (line_h + line_gap), line, font, fill)

    def _font_space(self, size: int, weight: int = 400):
        return load_font("space", size=size, weight=weight)

    def _font_inter(self, size: int, weight: int = 400):
        return load_font("inter", size=size, weight=weight)

    def _font_symbols(self, size: int, fill: int = 0):
        return load_font("symbols", size=size, fill=fill, weight=400, optical_size=min(max(size, 20), 48))

    def _text_width(self, draw: ImageDraw.ImageDraw, text: str, font) -> int:
        if not text:
            return 0
        return int(draw.textlength(text, font=font))

    def _text_height(self, draw: ImageDraw.ImageDraw, text: str, font) -> int:
        if not text:
            return 0
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[3] - bbox[1]

    def _ellipsize(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return ""
        if self._text_width(draw, cleaned, font) <= max_width:
            return cleaned
        ellipsis = "..."
        base = cleaned
        while base and self._text_width(draw, f"{base}{ellipsis}", font) > max_width:
            base = base[:-1].rstrip()
        return f"{base}{ellipsis}" if base else ellipsis

    def _clamp_lines(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        max_width: int,
        max_lines: int,
    ) -> list[str]:
        words = " ".join((text or "").split()).split(" ")
        if not words or words == [""]:
            return [""]

        lines: list[str] = []
        current = words[0]
        index = 1
        while index < len(words):
            word = words[index]
            candidate = f"{current} {word}".strip()
            if self._text_width(draw, candidate, font) <= max_width:
                current = candidate
                index += 1
                continue
            lines.append(current if self._text_width(draw, current, font) <= max_width else self._ellipsize(draw, current, font, max_width))
            current = word
            index += 1
            if len(lines) == max_lines - 1:
                remainder = " ".join([current, *words[index:]]).strip()
                lines.append(self._ellipsize(draw, remainder, font, max_width))
                return lines[:max_lines]
        lines.append(current if self._text_width(draw, current, font) <= max_width else self._ellipsize(draw, current, font, max_width))
        return lines[:max_lines]

    def _headline_subset_to_fit(
        self,
        draw: ImageDraw.ImageDraw,
        headlines: Sequence,
        usable_w: int,
        available_h: int,
        meta_font,
        headline_font,
        *,
        max_lines: int,
        counts: Iterable[int],
    ) -> list:
        meta_h = self._text_height(draw, "REUTERS", meta_font)
        headline_h = self._text_height(draw, "Ag", headline_font)

        def estimate_height(items: Sequence, divider_gap: int) -> int:
            height = 0
            for index, headline in enumerate(items):
                lines = self._clamp_lines(draw, headline.title, headline_font, usable_w, max_lines)
                height += meta_h + 8 + (len(lines) * headline_h) + (max(0, len(lines) - 1) * 2) + 14
                if index < len(items) - 1:
                    height += divider_gap + 1
            return height

        for count in counts:
            subset = list(headlines[:count])
            if subset and estimate_height(subset, 12) <= available_h:
                return subset

        for count in range(min(len(headlines), 6), 0, -1):
            subset = list(headlines[:count])
            if estimate_height(subset, 12) <= available_h:
                return subset
        return list(headlines[:1])

    def _weekday_row_slots(self, draw: ImageDraw.ImageDraw, right: int, time_font, due_font) -> tuple[int, int, int]:
        due_slot = max(
            self._text_width(draw, "(00m)", due_font),
            self._text_width(draw, "(000m)", due_font),
            self._text_width(draw, "(due)", due_font),
        )
        time_slot = self._text_width(draw, "00:00", time_font)
        due_anchor_right = right
        time_anchor_right = right - due_slot - 28
        destination_right = time_anchor_right - time_slot - 20
        return due_anchor_right, time_anchor_right, destination_right

    def _fit_hero_destination(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        max_width: int,
        max_height: int,
        base_size: int = 32,
        min_single_line_size: int = 24,
        min_wrap_size: int = 20,
    ) -> tuple[list[str], object]:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return [""], self._font_space(base_size, 700)

        base_font = self._font_space(base_size, 700)
        if self._text_width(draw, cleaned, base_font) <= max_width:
            return [cleaned], base_font

        for size in range(base_size - 2, min_single_line_size - 1, -2):
            font = self._font_space(size, 700)
            if self._text_width(draw, cleaned, font) <= max_width:
                return [cleaned], font

        for size in range(min_single_line_size, min_wrap_size - 1, -2):
            font = self._font_space(size, 700)
            lines = self._clamp_lines(draw, cleaned, font, max_width, 2)
            total_height = len(lines) * self._text_height(draw, "Ag", font)
            if len(lines) <= 2 and total_height <= max_height:
                return lines, font

        font = self._font_space(min_wrap_size, 700)
        lines = self._clamp_lines(draw, cleaned, font, max_width, 2)
        return lines, font

    def _fit_weather_detail_lines(
        self,
        draw: ImageDraw.ImageDraw,
        condition: str,
        high_low: str | None,
        primary_font,
        secondary_font,
        max_width: int,
    ) -> tuple[str, str | None]:
        condition_text = " ".join((condition or "").split())
        if not high_low:
            return self._ellipsize(draw, condition_text, primary_font, max_width), None

        combined = f"{condition_text}  |  {high_low}"
        if self._text_width(draw, combined, primary_font) <= max_width:
            return combined, None

        return (
            self._ellipsize(draw, condition_text, primary_font, max_width),
            self._ellipsize(draw, high_low, secondary_font, max_width),
        )

    def _fit_solar_market_sections(
        self,
        *,
        metrics_bottom: int,
        solar_block_height: int,
        market_section_height: int,
        bottom_margin: int,
        minimum_gap_after_metrics: int,
        minimum_gap_before_market: int,
    ) -> tuple[int, int, int]:
        market_divider_y = SETTINGS.height - bottom_margin - market_section_height
        latest_solar_top = market_divider_y - minimum_gap_before_market - solar_block_height
        solar_top = min(metrics_bottom + minimum_gap_after_metrics, latest_solar_top)
        market_top = market_divider_y + 8
        return solar_top, market_divider_y, market_top

    def _format_temperature(self, value: float | None) -> str:
        if value is None:
            return f"--{DEGREE}C"
        return f"{round(value):.0f}{DEGREE}C"

    def _format_high_low(self, weather) -> str | None:
        if weather.daily_high_c is None and weather.daily_low_c is None:
            return None
        high = f"H {self._format_temperature(weather.daily_high_c)}" if weather.daily_high_c is not None else None
        low = f"L {self._format_temperature(weather.daily_low_c)}" if weather.daily_low_c is not None else None
        return "  ".join(part for part in (high, low) if part)

    def _format_percent(self, value: float | int | None) -> str:
        if value is None:
            return "--"
        return f"{round(float(value)):.0f}%"

    def _format_aqi(self, index: int | None, label: str | None) -> str:
        if index is None:
            return "UNAVAILABLE"
        if label:
            return f"{index} {label.upper()}"
        return str(index)

    def _format_market_value(self, value: float | None) -> str:
        if value is None:
            return "--"
        if abs(value) >= 1000:
            return f"{value:,.2f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def _format_market_raw_change(self, value: float | None) -> str:
        if value is None:
            return "--"
        return f"{value:+,.2f}".rstrip("0").rstrip(".")

    def _format_market_percent(self, value: float | None) -> str:
        if value is None:
            return "--"
        return f"{value:+.2f}%"

    def _format_market_line(self, market: MarketIndexItem) -> str:
        return (
            f"{self._format_market_value(market.current_value)}  "
            f"{self._format_market_raw_change(market.raw_change)}  "
            f"{self._format_market_percent(market.percent_change)}"
        )

    def _format_clock(self, value: datetime | None) -> str:
        if value is None:
            return "--:--"
        return value.astimezone(LOCAL_TZ).strftime("%H:%M")

    def _format_departure_time(self, departure: BusDepartureItem) -> str:
        target = departure.expected_at or departure.scheduled_at
        return self._format_clock(target)

    def _format_due_minutes(self, value: int | None) -> str:
        if value is None:
            return "--"
        if value <= 0:
            return "due"
        return f"{value}m"

    def _uppercase_due(self, value: int | None) -> str:
        if value is None:
            return "--"
        if value <= 0:
            return "DUE"
        return f"{value:02d} MIN"

    def _split_due_label(self, due_label: str) -> tuple[str, str]:
        cleaned = " ".join((due_label or "").strip().upper().split())
        if not cleaned:
            return "--", ""
        parts = cleaned.split(" ", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]
