/*jslint vars:true, browser:true, nomen:true */
/*global document:true, jQuery:true, $:true */

/* TODO:
   Fix remaining jslint warnings: postfix operators, == comparision and eval */

$(document).ready(function () {
    "use strict";

    $('.ts').timeago();

    $('.ttip[title]').qtip({
        style: {
            background: '#fdfbc0',
            textAlign: 'left',
            lineHeight: '1.3em',
            color: '#333',
            border: {
                width: 1,
                color: '#e7e5a3',
                radius: 0
            },
            tip: 'topMiddle',
            name: 'cream'
        },
        position: {
            corner: {
                target: 'bottomMiddle',
                tooltip: 'topMiddle'
            }
        },
        show: {
            delay: 400
        }
    });

    $('.otip[title]').qtip({
        style: {
            background: '#fdfbc0',
            textAlign: 'left',
            lineHeight: '1.3em',
            color: '#333',
            border: {
                width: 1,
                color: '#e7e5a3',
                radius: 0
            },
            tip: 'bottomMiddle',
            name: 'cream'
        },
        position: {
            corner: {
                target: 'topMiddle',
                tooltip: 'bottomMiddle'
            }
        },
        show: {
            delay: 400
        }
    });


    $(".hidejs").hide();
    $(".showjs").show();


    var moreTags = function () {
        $(".moreTags").show();
        $(".moreTagsLink").hide();
        return false;
    };

    /* Tag area add form */
    var addTags = function (id) {
        $(".addtags").slideToggle('fast');
        return false;
    };

    /* Auto-appends */
    var appendAlternative = function () {
        var newElem;
        newElem = $(".alternative.prototype").clone();
        newElem.removeClass('prototype');
        newElem.slideDown('fast');
        newElem = newElem.insertAfter($(".alternative:last"));
        return false;
    };

    $(".userCompleted").autocomplete('/user/complete', {
        autoFill: false,
        dataType: 'json',
        formatItem: function (data, i, max, val) {
            return data.display;
        },
        formatResult: function (data, i, max, val) {
            return data.user;
        },
        parse: function (data) {
            var arr = [],
                i;
            for (i = 0; i < data.length; i++) {
                arr[i] = {data: data[i], value: data[i].display,
                          result: data[i].user};
            }
            return arr;
        },
        delay: 10
    });

    $("#tags").autocomplete('/tag/autocomplete', {
        autoFill: false,
        dataType: 'json',
        formatItem: function (data, i, max, val) {
            return data.display;
        },
        formatResult: function (data, i, max, val) {
            return data.tag;
        },
        parse: function (data) {
            var arr = [],
                i;
            for (i = 0; i < data.length; i++) {
                arr[i] = {data: data[i], value: data[i].display,
                          result: data[i].tag};
            }
            return arr;
        },
        delay: 10
    });

    var comment_reply = function (id) {
        $("#tile_c" + id + " .reply_form").slideToggle('fast');
        return false;
    };

    var comment_edit = function (id) {
        $("#tile_c" + id + " .pre").toggle();
        $("#tile_c" + id + " .hide_edit").slideToggle('fast');
        $("#tile_c" + id + " .edit_form").slideToggle('fast');
        return false;
    };

    var rate = function (elem_id, poll_id, value) {
        $(elem_id + " .score").text('*');
        $.post('/poll/' + poll_id + '/rate.json', {position: value},
            function (data) {
                $(elem_id + ".upvoted").removeClass("upvoted");
                $(elem_id + ".downvoted").removeClass("downvoted");
                if (data.decision && data.decision.decided) {
                    if (data.decision.result == -1) {
                        $(elem_id).addClass("downvoted");
                    }
                    if (data.decision.result == 1) {
                        $(elem_id).addClass("upvoted");
                    }
                }
                $(elem_id + " .score").text(data.tally.score);
                $(elem_id + " .num_for").text(data.tally.num_for);
                $(elem_id + " .num_against").text(data.tally.num_against);
            }, 'json');
        return false;
    };

    /* Low-scoring comments */
    var toggle_comment = function (id) {
        $("#c" + id).slideToggle('fast');
        $("#tc" + id).toggle();
        return false;
    };

    $('.normedit').keydown(function (e) {
        var ss = this.selectionStart;
        var se = this.selectionEnd;
        var scrollTop = this.scrollTop;

        if (e.which == 9) {
            var tab = '    ';
            this.value = this.value.substring(0, ss) + tab + this.value.substring(se, this.value.length);
            this.focus();
            ss = ss + tab.length;
            this.setSelectionRange(ss, ss);
            e.preventDefault();
        }

        this.scrollTop = scrollTop;
    });

    $('.discuss_details').hide();
    $('.discuss_button').show();
    $('.discuss_button').css('display', 'inline-block');
    $('.discuss_button').click(function (e) {
        $(this).hide();
        $(this).siblings('.discuss_details').show();
    });

    /* Mark up the comment selected via a URL anchor (i.e. after editing and creation) */
    var anchor = document.location.hash;
    if (anchor.length > 1) {
        $("#tile_" + anchor.substring(1)).addClass("anchor");
        $("#tile_" + anchor.substring(1)).parents().show();
        $("#tile_" + anchor.substring(1)).parents('.discuss').children('.discuss_button').hide();
        setTimeout(function () {
            $("#tile_" + anchor.substring(1)).removeClass("anchor");
        }, 3500);
    }

    /* Live filter for issue listing on instance home page */
    var originalListing = null;
    var timeoutSet = false;

    var live_filter = function (id, url) {
        $("#" + id + "_q").keyup(function (fld) {
            var _load = function () {
                if (!originalListing) {
                    originalListing = $("#" + id + "_table").html();
                }
                var destination = $("#" + id + "_table");
                var value = $.trim($("#" + id + "_q").val());
                if (value.length == 0) {
                    destination.html(originalListing);
                }
                var get_url = url + '?' + id + '_q=' + value;
                $.get(get_url, function (data, status) {
                    destination.html(data);
                }, 'text');
                timeoutSet = false;
            };
            if (!timeoutSet) {
                setTimeout(_load, 500);
                timeoutSet = true;
            }
        });
    };

    live_filter('users', '/user/filter');
    live_filter('serp', '/search/filter');
    live_filter('proposals', '/proposal/filter');


    $("#diff_left_select").change(function (e) {
        $("#diff_left_form").submit();
    });

    /* Armed labels: Use label text as pre-filling text for empty form fields. */
    $(".armlabel").each(function (e) {
        var hint = $("[for=" + $(this).attr("name") + "]").text();
        var field = this;

        $(this).focus(function () {
            if ($(field).hasClass("armed")) {
                $(field).val("");
                $(field).removeClass("armed");
            }
        });

        $(this).blur(function () {
            if ($.trim($(field).val()).length === 0) {
                $(field).val(hint);
                $(field).addClass("armed");
            }
        });
        $(this).blur();
    });

    /* Make sure that we do not submit placeholder texts */
    $("form").submit(function () {
        $(".armed").each(function (i) {
            $(this).val("");
        });
    });

    var showHelp = function (url) {
        var id = new Date().getTime();
        /* Fixme: eval is evil ;). AFAICR we want to use overlay dialogs here anyway. */
        eval("page" + id + " = window.open(url, '" + id + "', 'toolbar=0,scrollbars=1,location=0," +
             "statusbar=0,menubar=0,resizable=1,width=500,height=500');");
        return false;
    };

    var fixIE7Rendering = function () {
        if (!$.browser.msie || $.browser.version > 7) {
            return;
        }

        // Give layout to logo
        $('#header #logo *').css('zoom', 1);
        // Show Logo at right location
        $('#header #logo').css('top', 0);

        // show menu at about right height
        $('#header #menu *').css('zoom', 1);
        $('#header #menu').css('top', 50);
        $('#header #menu li *').css('width', 100);
        $('#header #menu li *').css('min-width', 100);

        // shows search box at appropriately right place
        $('#header #searchform *').css('zoom', 1);
        $('#header #searchform').css('top', 50);

        //FIXME: FIX THE (X)HTML to get browsers out of quirksmode! Otherwise IE debugging is wasted time
        // TODO: get image out of ul
    };

    fixIE7Rendering();

    /* jQuery UI stuff */
    //$("#accordion").accordion({ autoHeight: false });

    $(".expand_tab").click(function (e) {
        var title = $(this).attr('title').split('@');
        $('#' + title[1] + " .expand_area").hide();
        $('#' + title[1] + " .expand_tab").removeClass('area_shown');
        $('#' + title[1] + ' #' + title[0]).show();
        $(this).addClass('area_shown');
    });

    $(".expand_area.area_hidden").hide();
    $(".expand_tab").each(function (e) {
        var title = $(this).attr('title').split('@');

        if ($('#' + title[0]).is(":visible")) {
            $(this).addClass('area_shown');
        } else {
            $(this).removeClass('area_shown');
        }
    });

    /* if a tab contains an active anchor, open it: */
    var location = document.location.toString();
    if (location.match('#')) {
        var id = '#' + location.split('#')[1];
        $(".expand_area").each(function () {
            $("#" + this.id + ":has(" + id + ")").each(function () {
                $(".expand_tab[title*=" + this.id + "]").click();
            });
        });
    }
});

//Proposal badgets javascript
$(document).ready(function () {
    "use strict";
    //hide save button in proposal listing:
    $(".badgetsform_save").hide();
    //onClick submit form
    $(".badgetsform_input").click(function () {
        $(this).parent().submit();
    });
});
