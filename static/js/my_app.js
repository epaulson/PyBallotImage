console.log("Started for real")
//$('#imgHolder').prepend($('<img>',{id:'ballotImg',src:'/image', width: "100%"}))

var targets = {
  "raw_image": "/raw",
  "scored_image": "/scored_image",
  "dewarped_image":"/dewarped_image",
  "debug_style_image": "/debug/style_image",
  'debug_pass1_candidate_blocks_tight': "/debug/pass1_candidate_blocks_tight",
  "debug_phase1_candidate_lines_image": "/debug/pass1_line_image",
  "debug_phase2_candidate_lines_image": "/debug/pass2_line_image",

};

var currentFilter = "raw_image";
var currentImageId = null;


function updateImage()  {
  // https://stackoverflow.com/questions/15698241/swap-image-src-with-jquery
  var newsrc = "/image/" + currentImageId + targets[currentFilter];
  
  if ($('#imgHolder').src === "") {
    $('#imgHolder').fadeIn(200)[0].src = newsrc;
    $('#imgHolderA').attr("href", newsrc);
    
  } else {
    $('#imgHolder').fadeOut(200,function(){
      $('#imgHolder').fadeIn(200)[0].src = newsrc;
      $('#imgHolderA').attr("href", newsrc);
    });
  }
  
}

function onNodeSelectedHandler(event, data) {
  //console.log("a thing happend!");
  //console.log(event);
  //console.log(data);
  //getActiveTab($('#navs'))
  //var a = $('#appnav');
  //console.log(a);
  //console.log("Ran getActiveTab");
  window.counter = data['nodeId'];
  var targetImg = data['text'];
  currentImageId = targetImg;
  updateImage();
  //$('#imgHolder').attr("src", "/image/" + targetImg + "/processed");
  //$('#imgHolderRaw').attr("src", "/image/" + targetImg + "/raw");
  $.ajax("/image/" + targetImg + "/scored_json").done(function (msg) {
    var label = $('#jsonresults');
    var message = "Style: " + msg["style"] + "\nDetected Style: " + msg["detectedStyle"] + "\nStyleFile: " + msg["styleFile"] + "\nExpressVote: " + msg["expressVote"] + "\n\n";
    var races = msg["votes"]
    $.each(races, function (i, race) {
      var pixel_pcts = "";
      $.each(race["pixels"], function (k, v) {
        var tempstring = k + ": " + v + "\n";
        pixel_pcts += tempstring;
      });
      var tempstring = race["race"] + ":\n" + "ESS: " + race["details"]["ESS"] + "\n" + "Scored: " + race["details"]["scored"] + "\n\n" + pixel_pcts + "\n\n";
      //var tempstring = race["race"] + ":\n" + "ESS: " + race["details"]["ESS"] + "\n" + "Scored: " + race["details"]["scored"] + "\n\n";
      message += tempstring;
    });
    label.text(message);
    label.html(label.html().replace(/\n/g, '<br/>'));
  });
}; 

$(document).ready(function () {
  lightbox.option({
    'resizeDuration': 200,
    'wrapAround': true
  })
  $.getJSON("/images/", function (d) {
    //console.log("Success in load!");
    //console.log([d]);
    $('#tree').treeview({ data: d, onNodeSelected: onNodeSelectedHandler });
    $('#tree').css('max-height', '1200px')
    $('#tree').css('overflow', 'scroll');
    $('#tree').treeview('selectNode', [1, { silent: false }]);
  })
  // https://stackoverflow.com/questions/13437446/how-to-display-selected-item-in-bootstrap-button-dropdown-title
  $(".dropdown-menu li a").click(function(){
    //console.log("Logging this");
    //console.log($(this).text());
    //console.log($(this).data('value'));
    $(this).parents(".dropdown").find('.btn').html($(this).text() + ' <span class="caret"></span>');
    $(this).parents(".dropdown").find('.btn').val($(this).data('value'));
    currentFilter = $(this).data('value');
    updateImage();
  });
});

var counter = 2
$(document).keydown(function(e) {
    switch(e.which) {
        case 37: // left
        break;

        case 38: // up
        console.log("selecting up next node");
        if(window.counter > 1 ) {
          $('#tree').treeview('selectNode', [ window.counter-1, { silent: false } ]);
        }
        else {
          console.log("cant go under")
        }
        break;

        case 39: // right
        break;

        case 40: // down
        console.log("selecting down next node");
        if(window.counter < 100) {
          $('#tree').treeview('selectNode', [ window.counter+1, { silent: false } ]);
        }
        else {
          console.log("cant go over")
        }
        break;

        default: return; // exit this handler for other keys
    }
    e.preventDefault(); // prevent the default action (scroll / move caret)
});

