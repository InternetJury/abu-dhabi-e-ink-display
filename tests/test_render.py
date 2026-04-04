from hashlib import sha1

from PIL import Image, ImageDraw

from ribbon.fixtures import load_fixture_snapshot
from ribbon.models import MarketDirection, MarketIndexItem
from ribbon.render import RibbonRenderer


def test_renderer_outputs_exact_canvas_size_for_primary_modes():
    for fixture_name in ("weekday_commute_now", "weekend_multi_stop", "ambient_info"):
        snapshot = load_fixture_snapshot(fixture_name)
        image = RibbonRenderer().render(snapshot)
        assert image.size == (1360, 480)


def test_weekend_centered_stop_name_variant_keeps_canvas_size():
    snapshot = load_fixture_snapshot("weekend_multi_stop")
    image = RibbonRenderer(center_weekend_stop_names=True).render(snapshot)
    assert image.size == (1360, 480)


def test_weekday_center_crop_matches_locked_reference_hash():
    snapshot = load_fixture_snapshot("weekday_commute_now")
    image = RibbonRenderer().render(snapshot)
    center_crop = image.crop((250, 0, 1010, 480))
    assert sha1(center_crop.tobytes()).hexdigest() == "379f1d49cb758d48d1bafe996ae808a26e6cacfd"


def test_weekend_render_matches_locked_reference_hash():
    snapshot = load_fixture_snapshot("weekend_multi_stop")
    image = RibbonRenderer().render(snapshot)
    assert sha1(image.tobytes()).hexdigest() == "f0d4aea25eb35de910e264d89943218a50172a04"


def test_weekday_hero_destination_hybrid_fit_stays_inside_safe_width():
    renderer = RibbonRenderer()
    draw = ImageDraw.Draw(Image.new("L", (1360, 480), 255))
    lines, font = renderer._fit_hero_destination(
        draw,
        "ABU DHABI / MAIN BUS STATION / CULTURAL FOUNDATION / CENTRAL TERMINAL",
        max_width=280,
        max_height=42,
    )

    assert 1 <= len(lines) <= 2
    assert all(renderer._text_width(draw, line, font) <= 280 for line in lines)
    assert len(lines) * renderer._text_height(draw, "Ag", font) <= 42


def test_weather_detail_lines_split_to_fit_narrow_rail_width():
    renderer = RibbonRenderer()
    draw = ImageDraw.Draw(Image.new("L", (1360, 480), 255))
    primary_font = renderer._font_inter(17, 700)
    secondary_font = renderer._font_inter(15, 700)

    detail_line, detail_subline = renderer._fit_weather_detail_lines(
        draw,
        "OVERCAST",
        "H 26°C  L 22°C",
        primary_font,
        secondary_font,
        170,
    )

    assert renderer._text_width(draw, detail_line, primary_font) <= 170
    assert detail_subline is not None
    assert renderer._text_width(draw, detail_subline, secondary_font) <= 170


def test_solar_market_sections_reserve_clear_gap():
    renderer = RibbonRenderer()
    solar_top, market_divider_y, _ = renderer._fit_solar_market_sections(
        metrics_bottom=310,
        solar_block_height=40,
        market_section_height=58,
        bottom_margin=18,
        minimum_gap_after_metrics=16,
        minimum_gap_before_market=14,
    )

    assert solar_top >= 326
    assert solar_top + 40 <= market_divider_y - 14


def test_market_line_uses_signed_numbers_without_inline_direction_glyphs():
    renderer = RibbonRenderer()
    text = renderer._format_market_line(
        MarketIndexItem(
            code="NIFTY",
            label="NIFTY",
            current_value=22713.1,
            raw_change=33.7,
            percent_change=0.15,
            direction=MarketDirection.UP,
        )
    )

    assert "22,713.1" in text
    assert "+33.7" in text
    assert "+0.15%" in text
    assert "▲" not in text
    assert "▼" not in text
    assert "▬" not in text
    assert "?" not in text


def test_weekday_row_slots_keep_shared_time_and_due_anchors():
    renderer = RibbonRenderer()
    draw = ImageDraw.Draw(Image.new("L", (1360, 480), 255))
    due_anchor_right, time_anchor_right, destination_right = renderer._weekday_row_slots(
        draw,
        978,
        renderer._font_space(20, 500),
        renderer._font_space(20, 700),
    )

    assert due_anchor_right == 978
    assert time_anchor_right < due_anchor_right
    assert destination_right < time_anchor_right
